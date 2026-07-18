"""Cleanup saga: audit (pi agent) -> purge (code).

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
"""
from __future__ import annotations

import json
from pathlib import Path

import jsonschema

from .store import Store

CLEANUP_STAGES = ["audit", "purge"]
CLEANUP_AGENT_STAGES = {"audit"}

_SCHEMA = json.loads(
    (Path(__file__).resolve().parent.parent / "schemas" / "cleanup.json").read_text()
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
    """Same provenance-field recursion as sagas._count_populated."""
    if isinstance(node, dict):
        if "value" in node and "confidence" in node:
            v = node.get("value")
            return 0 if v is None or v == [] or v == "" else 1
        return sum(_count_populated(v) for v in node.values())
    if isinstance(node, list):
        return sum(_count_populated(v) for v in node)
    return 0


async def candidates(store: Store, prefix: str) -> list[dict]:
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


async def start(store: Store, prefix: str, *, trace_id: str) -> tuple[str, int]:
    """Create the cleanup saga for an id prefix and enqueue its audit job."""
    cands = await candidates(store, prefix)
    saga_id = saga_id_for(prefix)
    await store.create_saga(saga_id, "cleanup", prefix,
                            current_step="audit", trace_id=trace_id)
    await store.enqueue_job(saga_id, "audit", target_id=prefix,
                            agent="janitor", trace_id=trace_id)
    return saga_id, len(cands)


async def build_prompt(job, store: Store) -> str:
    prefix = job["target_id"]
    cands = await candidates(store, prefix)
    retry = (job["attempts"] or 0) > 1
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


async def persist_and_advance(store: Store, job, data: dict) -> None:
    """audit: record the verdict artifact, then advance to the purge code stage."""
    saga_id, prefix, trace_id = job["saga_id"], job["target_id"], job["trace_id"]
    await store.record_artifact(saga_id, "audit", data,
                                target_id=prefix, trace_id=trace_id)
    deletes = sum(1 for v in data.get("verdicts", []) if v.get("action") == "delete")
    await store.finish_stage(
        job_id=job["id"], saga_id=saga_id, event_kind="CleanupAudited",
        saga_step="purge", saga_status="running",
        event_payload={"prefix": prefix, "candidates": len(data.get("verdicts", [])),
                       "delete_verdicts": deletes},
        trace_id=trace_id,
        next_stage="purge", next_target_id=prefix,
        next_input_ref={"from": "audit"},
    )


async def purge(store: Store, job) -> None:
    """Code stage: delete verdicted-delete ids (prefix rail enforced here)."""
    saga_id, prefix, trace_id = job["saga_id"], job["target_id"], job["trace_id"]
    art = await store.get_artifact(saga_id, "audit", prefix) or {}
    verdicts = art.get("verdicts") or []
    delete_ids = [v["id"] for v in verdicts
                  if v.get("action") == "delete"
                  and isinstance(v.get("id"), str) and v["id"].startswith(prefix)]
    kept = [v["id"] for v in verdicts if v.get("action") == "keep"]
    counts = await store.delete_entities(delete_ids) if delete_ids else {}
    await store.finish_stage(
        job_id=job["id"], saga_id=saga_id, event_kind="CleanupCompleted",
        saga_step="purge", saga_status="done",
        event_payload={"prefix": prefix, "deleted": delete_ids, "kept": kept,
                       "rows_deleted": counts},
        trace_id=trace_id,
    )
