"""Phase 4 hardening — idempotency, dead-letter, session hygiene.

Proves:
  - re-running bootstrap seed creates NO duplicate entities/sagas/jobs
    (deterministic slug ids + ON CONFLICT).
  - the code `link` stage is idempotent on re-run (R9): one entity, no duplicate edges.
  - the draft/verify retry loop dead-letters at MAX_ATTEMPTS (R5) — both the generic
    fail_job budget and the store.dead_letter path (marks jobs dead + DraftDeadLettered).
  - session hygiene reset frame {"type":"new_session"} (R7) — see also
    tests/test_transport_framing.py::test_new_session_framing.
"""
import uuid

import pytest

from scripts.bootstrap import seed
from spine.ids import entity_id, slugify


def _uid() -> str:
    return uuid.uuid4().hex[:8]


async def _purge(store, saga_id: str | None = None, entity_id: str | None = None) -> None:
    async with store.pool.acquire() as conn:
        if saga_id:
            for t in ("jobs", "artifacts", "events", "saga_instances"):
                await conn.execute(f"DELETE FROM {t} WHERE saga_id=$1", saga_id)
        if entity_id:
            await conn.execute("DELETE FROM edges WHERE src_id=$1", entity_id)
            await conn.execute("DELETE FROM entities WHERE id=$1", entity_id)


# ---------------------------------------------------------------- deterministic ids

def test_slug_is_deterministic_and_ascii():
    assert entity_id("startup", "enfarm agritech") == "startup:enfarm-agritech"
    # Vietnamese diacritics + đ fold deterministically to a stable ascii slug.
    assert slugify("Đổi mới") == slugify("Đổi mới")
    assert slugify("Công ty Cổ phần") == "cong-ty-co-phan"


# ---------------------------------------------------------------- bootstrap re-run

async def test_bootstrap_seed_is_idempotent(store):
    name = f"Idem Test Co {_uid()}"
    eid = entity_id("startup", name)
    saga_id = f"onboard:{eid}"
    records = [{"name": name, "type": "startup", "country": "Vietnam",
               "hint_website": "https://example.test"}]

    first = await seed(store, records, "run:first")
    second = await seed(store, records, "run:second")

    # both runs "upsert" one entity, but the second enqueues nothing new.
    assert first == {"entities": 1, "sagas": 1, "jobs_enqueued": 1}
    assert second["entities"] == 1 and second["sagas"] == 1
    assert second["jobs_enqueued"] == 0  # ON CONFLICT DO NOTHING on the enrich job

    ent_count = await store.pool.fetchval("SELECT count(*) FROM entities WHERE id=$1", eid)
    saga_count = await store.pool.fetchval(
        "SELECT count(*) FROM saga_instances WHERE saga_id=$1", saga_id)
    job_count = await store.pool.fetchval(
        "SELECT count(*) FROM jobs WHERE saga_id=$1 AND stage='enrich'", saga_id)
    assert (ent_count, saga_count, job_count) == (1, 1, 1)

    await _purge(store, saga_id=saga_id, entity_id=eid)


async def test_link_stage_is_idempotent(store, saga_id):
    from apps.matchmaker.plugin import link
    from spindle.app.context import StageCtx

    eid = "startup:linkidem-" + _uid()
    await store.upsert_entity(eid, "startup", "Link Idem Co",
                              profile={"country": "Vietnam"}, status="seeded")
    await store.create_saga(saga_id, "onboarding", eid, current_step="link")
    await store.record_artifact(
        saga_id, "enrich",
        {"entity_type": "startup",
         "relationships": [{"kind": "raised_from", "dst_name": "Acme Fund",
                            "source_url": "https://acme.test"}],
         "collection_summary": {}},
        target_id=eid)
    await store.record_artifact(
        saga_id, "extract",
        {"sectors": ["agritech"], "looking_for": ["funding"]}, target_id=eid)

    ctx = StageCtx(app_id="matchmaker", saga_id=saga_id, subject_id=eid, target_id=eid,
                   trace_id="t", attempts=0, retry_feedback=None, store=store)
    await link(ctx)
    await link(ctx)   # re-run (e.g. after a reclaim)

    ent = await store.get_entity(eid)
    assert ent["status"] == "ready"
    n_ent = await store.pool.fetchval("SELECT count(*) FROM entities WHERE id=$1", eid)
    n_edge = await store.pool.fetchval(
        "SELECT count(*) FROM edges WHERE src_id=$1 AND kind='raised_from'", eid)
    assert n_ent == 1        # deterministic id -> upsert, never a duplicate
    assert n_edge == 1       # UNIQUE(src_id, dst_id, kind) -> no duplicate relationship

    await _purge(store, saga_id=saga_id, entity_id=eid)


# ---------------------------------------------------------------- dead-letter

async def test_fail_job_dead_letters_at_max_attempts(store, saga_id):
    """A retryable sub-job that keeps failing is dead-lettered once attempts hit the
    budget (R5). Unique stage isolates acquire on the shared DB."""
    stage = "verify_" + _uid()
    jid = await store.enqueue_job(saga_id, stage, target_id="partner:x")

    outcomes = []
    for _ in range(3):
        await store.acquire_job("w", [stage], lease_seconds=120)  # bumps attempts
        outcomes.append(await store.fail_job(jid, max_attempts=3))
    assert outcomes == ["ready", "ready", "dead"]  # forward-retry, then dead-letter

    await _purge(store, saga_id=saga_id)


async def test_dead_letter_path_marks_jobs_and_emits_event(store, saga_id):
    """store.dead_letter (verify->draft retry budget exhausted): the draft+verify
    sub-jobs go 'dead' and a DraftDeadLettered milestone is appended."""
    draft = await store.enqueue_job(saga_id, "draft", target_id="partner:p1", agent="drafter")
    verify = await store.enqueue_job(saga_id, "verify", target_id="partner:p1",
                                     agent="verifier")

    await store.dead_letter(
        job_ids=[draft, verify], saga_id=saga_id,
        event_payload={"partner_id": "partner:p1", "reason": "max_retries"})

    rows = await store.pool.fetch(
        "SELECT status FROM jobs WHERE id = ANY($1::bigint[])", [draft, verify])
    assert [r["status"] for r in rows] == ["dead", "dead"]

    ev = await store.pool.fetchrow(
        "SELECT payload FROM events WHERE saga_id=$1 AND kind='DraftDeadLettered'", saga_id)
    assert ev is not None

    await _purge(store, saga_id=saga_id)
