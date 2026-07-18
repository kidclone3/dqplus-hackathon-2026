"""Cleanup saga helpers: audit (pi agent) -> purge (code).

Prefix-scoped graph hygiene for junk entities (e.g. placeholder rows left by
aborted onboarding runs, id LIKE 'startup:saga_%'):

  audit  (pi, janitor)  per-candidate evidence -> delete/keep verdicts (R3,
                        schemas/cleanup.json)
  purge  (code)         delete verdicted ids from the graph tables

Drop-only rail: purge deletes ONLY ids that are both verdicted 'delete' AND
still match the requested prefix — the agent can spare entities, never widen
the blast radius. Operational history (saga_instances/jobs/events/artifacts/
llm_usage) is preserved; only graph data (entities, edges, matches, matches_v2)
is removed.

The stage bodies live in ``apps.matchmaker.plugin`` (``AuditStage`` /
``purge``); this module holds the evidence query, the prompt, and the R3
schema gate they share with ``scripts/cleanup.py``.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import TYPE_CHECKING

import jsonschema

if TYPE_CHECKING:
    from apps.matchmaker.store import MatchmakerStore

CLEANUP_STAGES = ["audit", "purge"]

_SCHEMA = json.loads(
    (Path(__file__).resolve().parents[2] / "schemas" / "cleanup.json").read_text()
)

_REMINDER = ("\n\nIMPORTANT: your previous reply was not valid. Respond with ONLY a "
             "single fenced ```json block and nothing else — no prose, no explanation.")


def saga_id_for(prefix: str) -> str:
    return f"cleanup:{prefix}"


def validate(data) -> bool:
    if not isinstance(data, dict):
        return False
    try:
        jsonschema.validate(data, _SCHEMA)
        return True
    except jsonschema.ValidationError:
        return False


def _count_populated(node) -> int:
    """Same provenance-field recursion as the link stage's field counter."""
    if isinstance(node, dict):
        if "value" in node and "confidence" in node:
            v = node.get("value")
            return 0 if v is None or v == [] or v == "" else 1
        return sum(_count_populated(v) for v in node.values())
    if isinstance(node, list):
        return sum(_count_populated(v) for v in node)
    return 0


async def candidates(store: "MatchmakerStore", prefix: str) -> list[dict]:
    """Evidence rows for every entity whose id starts with the prefix."""
    rows = await store.pool.fetch(
        """
        SELECT e.id, e.type, e.name, e.status, e.created_at::text AS created_at,
               e.profile,
               (SELECT count(*) FROM edges g
                 WHERE g.src_id = e.id OR g.dst_id = e.id)        AS edge_count,
               (SELECT count(*) FROM matches m
                 WHERE m.startup_id = e.id OR m.partner_id = e.id) AS match_count
        FROM entities e
        WHERE e.id LIKE $1 || '%'
        ORDER BY e.id
        """,
        prefix,
    )
    out = []
    for r in rows:
        profile = r["profile"]
        if isinstance(profile, str):
            profile = json.loads(profile) if profile else {}
        profile = profile or {}
        seed = profile.get("seed") or {}
        normalized = profile.get("normalized") or {}
        out.append({
            "id": r["id"],
            "type": r["type"],
            "name": r["name"],
            "status": r["status"],
            "created_at": r["created_at"],
            "name_is_placeholder": r["name"] == r["id"],
            "seed_fields": len(seed) if isinstance(seed, dict) else 1,
            "normalized_fields": len(normalized) if isinstance(normalized, dict) else 1,
            "populated_provenance_fields": _count_populated(profile),
            "edge_count": r["edge_count"],
            "match_count": r["match_count"],
        })
    return out


async def start(store: "MatchmakerStore", prefix: str, *, trace_id: str) -> tuple[str, int]:
    """Create the cleanup saga for an id prefix and enqueue its audit job."""
    cands = await candidates(store, prefix)
    saga_id = saga_id_for(prefix)
    await store.create_saga(saga_id, "cleanup", prefix,
                            current_step="audit", trace_id=trace_id)
    await store.enqueue_job(saga_id, "audit", target_id=prefix,
                            agent="janitor", trace_id=trace_id)
    return saga_id, len(cands)


def build_prompt(prefix: str, cands: list[dict], *, retry: bool = False) -> str:
    evidence = json.dumps(cands, ensure_ascii=False, indent=1)
    prompt = f"""You are the data janitor for Vietnam's National Innovation Center (NIC) \
deal-flow database. An operator asked to clean up entities whose id starts with \
"{prefix}" — suspected junk placeholders left behind by test/aborted saga runs.

CANDIDATES (evidence per entity):
{evidence}

Judge EVERY candidate:
- action "delete" — a junk placeholder or test artifact: tell-tale signs are \
name_is_placeholder=true (the display name is just the raw id), zero seed/normalized \
profile fields, and zero populated provenance fields. Such rows pollute matching.
- action "keep" — anything that looks like a REAL entity: a human-readable name, \
a non-trivial profile (seed/normalized/provenance fields), or evidence it was \
genuinely onboarded. When in doubt, KEEP — deletion is irreversible.

edge_count / match_count are informational only (referencing rows are cascaded by \
the purge step); they do NOT make an entity real.

OUTPUT (R3 contract): reply with ONLY a single fenced ```json block:
{{"verdicts": [{{"id": "<entity id>", "action": "delete"|"keep", "reason": "<short>"}}, ...],
 "summary": "<one line>"}}
Include a verdict for EVERY candidate id above, no others. No prose outside the JSON."""
    return prompt + (_REMINDER if retry else "")
