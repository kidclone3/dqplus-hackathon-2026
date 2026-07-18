"""Relationship-graph discovery (spec §5.1: edges "consumed by future GraphRAG").

This module re-resolves edge targets by name against the current entity set at query
time, working around the `dst_resolved` bug: the stored flag is set at write time by
the extraction/link pipeline, and it is effectively always false (654/655 rows in the
seed dataset) even when `dst_name` clearly matches an onboarded entity. Because
`spine/ids.py::slugify` is deterministic, we can slugify any edge's `dst_name` and
check for a match against the live entity table for free, with no schema change and
no re-running the pipeline.

This is NOT a Matcher implementation (it is independent of the Matcher protocol in
spine/matcher/__init__.py). It answers: "given a startup (or any entity), which
investors/corporations/etc. is it N hops from via a real (name-resolved) relationship
edge, and via what chain of relationships?" — a signal the LlmJudgeMatcher never sees,
since it only looks at one startup + its filtered candidate list at a time.

Usage:
    graph = build_graph(entities, edges)
    paths = graph.find_paths("startup:enfarm-agritech", max_hops=2,
                             target_types={"investor", "corporation"})
    for p in paths:
        print(path_to_dict(p))

On the seed dataset this signal is real but sparse (a minority of startups will have
any graph-discovered match). That is expected and honest — do not pad or fake results.
"""
from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field
from typing import Any

from .ids import slugify

# Edge kinds worth traversing for co-investment / partnership discovery.
# Includes capital-flavored and partnership-flavored relationships that connect
# companies to companies or companies to investors.
#
# This is the union of the reference fork's traversable set and the relational edge
# `kind` values this repo actually produces (spine/sagas.py `_ALLOWED_KINDS`,
# migrations/001_core.sql `edges.kind` examples) — `co_invested` and `same_sector` are
# the repo-specific additions — so both the ported tests and our real edges traverse.
#
# Excluded: `founded_by_alumni_of` — this is a biographical edge (person → institution
# where a founder studied or worked), not a company-to-company relationship. Traversing
# through it would collapse startups whose founders share an alma mater, which is a
# weak and noisy signal for deal-flow matching (two startups having founders from the
# same university does not mean they should be matched to each other).
RELATIONAL_KINDS = frozenset({
    "raised_from",
    "invested_in",
    "partner_with",
    "pilot_with",
    "distribution_partner_with",
    "mou_signed_with",
    "accelerator_selected_by",
    "accelerator_advised_by",
    "co_invested",
    "same_sector",
})


@dataclass(frozen=True)
class Hop:
    """A single edge in a graph traversal path."""
    from_id: str
    to_id: str
    kind: str
    source_url: str | None = None
    hop: int = 1


@dataclass
class GraphPath:
    """A shortest-path graph traversal result from start entity to target entity."""
    target_id: str
    target_name: str
    target_type: str
    hops: list[Hop] = field(default_factory=list)

    @property
    def distance(self) -> int:
        return len(self.hops)


class RelationshipGraph:
    """Undirected graph of entity relationships, built from plain dicts (no DB dependency).

    Re-resolves edge targets by:
      1. Checking if ``dst_id`` already matches a known entity id (the ideal case).
      2. Falling back to slugifying ``dst_name`` and looking it up in a slug→entity index.

    Edges whose target cannot be resolved (neither ``dst_id`` nor slugified ``dst_name``
    matches any known entity) are silently skipped — they point to something never
    onboarded and are genuinely not traversable.
    """

    def __init__(self, entities: list[dict], edges: list[dict]):
        # entity_id -> entity
        self._entities: dict[str, dict] = {e["id"]: e for e in entities}

        # slug(name) -> entity_id  (across ALL entity types, not just partners)
        self._slug_index: dict[str, str] = {}
        for e in entities:
            slug = slugify(e["name"])
            # If the same slug appears for multiple types (e.g. "FPT" as a startup and
            # as a corporation), prefer the exact entity_id match; otherwise just pick
            # the first — collisions are rare in practice and deduping is safe here
            # because the slug resolution is a best-effort fallback.
            if slug not in self._slug_index:
                self._slug_index[slug] = e["id"]

        # adjacency: entity_id -> list of (neighbor_id, kind, source_url)
        self._adj: dict[str, list[tuple[str, str, str | None]]] = {}

        for edge in edges:
            kind = edge.get("kind", "")
            if kind not in RELATIONAL_KINDS:
                continue

            src = edge["src_id"]
            resolved_id = self._resolve_target(edge)
            if resolved_id is None:
                continue  # edge points to something never onboarded

            # Add undirected (bidirectional) edges
            self._add_edge(src, resolved_id, kind, edge.get("source_url"))
            self._add_edge(resolved_id, src, kind, edge.get("source_url"))

    def _resolve_target(self, edge: dict) -> str | None:
        """Resolve an edge's target to a known entity id, or None if unresolvable."""
        dst_id = edge.get("dst_id", "")
        if dst_id in self._entities:
            return dst_id

        dst_name = edge.get("dst_name", "")
        if not dst_name:
            return None

        slug = slugify(dst_name)
        return self._slug_index.get(slug)

    def _add_edge(self, from_id: str, to_id: str, kind: str, source_url: str | None):
        if from_id not in self._entities:
            return
        if from_id not in self._adj:
            self._adj[from_id] = []
        # Avoid duplicate entries (same (from, to, kind) — guards against symmetric edges
        # from the bidirectional add)
        for existing_to, existing_kind, _ in self._adj[from_id]:
            if existing_to == to_id and existing_kind == kind:
                return
        self._adj[from_id].append((to_id, kind, source_url))

    def neighbors(self, entity_id: str) -> list[tuple[str, str, str | None]]:
        """Return list of (neighbor_id, kind, source_url) for a given entity."""
        return list(self._adj.get(entity_id, []))

    def find_paths(self, start_id: str, *, max_hops: int = 2,
                   target_types: set[str] | None = None) -> list[GraphPath]:
        """BFS from ``start_id``, shortest-path-only per node.

        Returns one ``GraphPath`` per reachable entity within ``max_hops``,
        optionally filtered to ``target_types`` (e.g. ``{"investor", "corporation"}``),
        sorted by distance ascending.
        """
        if start_id not in self._entities:
            return []

        start_entity = self._entities[start_id]

        # BFS state: node_id -> (parent_id, Hop used to reach it)
        visited: dict[str, tuple[str | None, Hop | None]] = {start_id: (None, None)}
        queue: deque[str] = deque([start_id])

        while queue:
            current = queue.popleft()

            # Reconstruct distance to current to respect max_hops
            dist = 0
            node = current
            while visited[node][0] is not None:
                dist += 1
                node = visited[node][0]  # type: ignore[arg-type]
            if dist >= max_hops:
                continue

            for neighbor_id, kind, source_url in self.neighbors(current):
                if neighbor_id not in visited:
                    visited[neighbor_id] = (
                        current,
                        Hop(from_id=current, to_id=neighbor_id, kind=kind,
                            source_url=source_url),
                    )
                    queue.append(neighbor_id)

        # Reconstruct paths from visited
        results: list[GraphPath] = []
        for node_id, (parent, _) in visited.items():
            if node_id == start_id:
                continue
            entity = self._entities.get(node_id)
            if entity is None:
                continue

            target_type = entity.get("type", "unknown")
            if target_types is not None and target_type not in target_types:
                continue

            # Walk backwards to build the hop chain
            hops: list[Hop] = []
            current_node = node_id
            while visited[current_node][1] is not None:
                hop = visited[current_node][1]
                assert hop is not None
                hops.append(hop)
                current_node = visited[current_node][0]  # type: ignore[arg-type]
            hops.reverse()

            # Assign 1-indexed hop numbers
            for i, h in enumerate(hops):
                hops[i] = Hop(from_id=h.from_id, to_id=h.to_id, kind=h.kind,
                              source_url=h.source_url, hop=i + 1)

            results.append(GraphPath(
                target_id=node_id,
                target_name=entity.get("name", node_id),
                target_type=target_type,
                hops=hops,
            ))

        results.sort(key=lambda p: p.distance)
        return results


def build_graph(entities: list[dict], edges: list[dict]) -> RelationshipGraph:
    """Factory: construct a ``RelationshipGraph`` from entity and edge dict lists."""
    return RelationshipGraph(entities, edges)


def path_to_dict(path: GraphPath) -> dict[str, Any]:
    """JSON-serializable representation of a ``GraphPath``.

    Returns::

        {
          "target_id": "...",
          "target_name": "...",
          "target_type": "...",
          "distance": 1,
          "path": [
            {"from_id": "...", "to_id": "...", "kind": "...",
             "source_url": "...", "hop": 1}
          ]
        }
    """
    return {
        "target_id": path.target_id,
        "target_name": path.target_name,
        "target_type": path.target_type,
        "distance": path.distance,
        "path": [
            {"from_id": h.from_id, "to_id": h.to_id, "kind": h.kind,
             "source_url": h.source_url, "hop": h.hop}
            for h in path.hops
        ],
    }
