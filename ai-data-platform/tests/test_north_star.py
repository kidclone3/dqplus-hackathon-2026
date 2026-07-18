import os

import pytest
import pytest_asyncio

from tests.harness import db as hdb

pytestmark = pytest.mark.north_star


@pytest_asyncio.fixture
async def ns_store():
    if not await hdb.db_reachable():
        # As the regression GATE (scripts/north_star.sh sets NORTH_STAR_REQUIRE_DB=1) a
        # down Postgres is a hard FAILURE, not a skip — a skipped gate is a green gate
        # that verified nothing, which would silently certify Phases 1–6 as safe.
        if os.environ.get("NORTH_STAR_REQUIRE_DB"):
            pytest.fail("Postgres unreachable but NORTH_STAR_REQUIRE_DB set "
                        "(run: docker compose up -d postgres)")
        pytest.skip("Postgres not reachable (run: docker compose up -d postgres)")
    dbname, store = await hdb.create_ephemeral()
    try:
        yield store
    finally:
        await hdb.drop_ephemeral(dbname, store)


async def test_ephemeral_db_has_platform_tables(ns_store):
    n = await ns_store.pool.fetchval(
        "SELECT count(*) FROM information_schema.tables "
        "WHERE table_name IN ('jobs','events','saga_instances','entities','matches')")
    assert n == 5


import json
from pathlib import Path

import jsonschema

from tests.harness.replay_launcher import STAGE_RESPONSES

_SCHEMAS = Path(__file__).resolve().parent.parent / "schemas"


@pytest.mark.parametrize("stage,schema_file", [
    ("enrich", "enrich.json"), ("extract", "extract.json"),
    ("match", "rank.json"), ("draft", "draft.json"), ("verify", "verify.json"),
])
def test_canned_responses_match_r3_schemas(stage, schema_file):
    schema = json.loads((_SCHEMAS / schema_file).read_text())
    prompt = '... "partner_id": "investor:seed-capital-vn" ...'  # match needs an id
    jsonschema.validate(STAGE_RESPONSES[stage](prompt), schema)


from tests.harness import fixtures


async def test_bootstrap_enqueues_one_enrich_per_entity(ns_store):
    startup_ids = await fixtures.seed_and_enqueue_onboarding(ns_store)
    assert len(startup_ids) == fixtures.STARTUP_COUNT
    n_entities = await ns_store.pool.fetchval("SELECT count(*) FROM entities")
    n_enrich = await ns_store.pool.fetchval(
        "SELECT count(*) FROM jobs WHERE stage='enrich' AND status='ready'")
    assert n_entities == fixtures.ENTITY_COUNT
    assert n_enrich == fixtures.ENTITY_COUNT


from spine.supervisor import Supervisor
from tests.harness.replay_launcher import ReplayLauncher


async def _drain(store):
    sup = Supervisor(store, launcher=ReplayLauncher(), reclaim_interval=0.2)
    await sup.run(drain=True)


async def test_north_star_a1_through_a5(ns_store):
    store = ns_store

    # A5: the cold-boot sequence, offline.
    startup_ids = await fixtures.seed_and_enqueue_onboarding(store)
    await _drain(store)                              # onboarding: enrich→extract→link
    await fixtures.enqueue_outreach(store, startup_ids)
    await _drain(store)                              # outreach: filter→match→draft→verify

    # A1: every entity onboarded to status='ready' with a normalized profile.
    ready = await store.pool.fetchval("SELECT count(*) FROM entities WHERE status='ready'")
    assert ready == fixtures.ENTITY_COUNT

    # A2: relationship edges written from enrich relationships — exactly one
    # `raised_from` edge per entity (UNIQUE(src_id,dst_id,kind) dedups re-runs).
    edges = await store.pool.fetchval("SELECT count(*) FROM edges")
    assert edges == fixtures.ENTITY_COUNT

    # A3: each startup has 5 verified bilingual draft_ready matches spanning types.
    for sid in startup_ids:
        n = await store.pool.fetchval(
            "SELECT count(*) FROM matches WHERE startup_id=$1 AND status='draft_ready' "
            "AND draft_en IS NOT NULL AND draft_vi IS NOT NULL", sid)
        assert n == 5, f"{sid} has {n} draft_ready matches, expected 5"
        types = {r["type"] for r in await store.pool.fetch(
            "SELECT DISTINCT e.type FROM matches m JOIN entities e ON e.id=m.partner_id "
            "WHERE m.startup_id=$1 AND m.status='draft_ready'", sid)}
        # cohort must SPAN partner types, not collapse to one (matcher/filter regressions)
        assert len(types) >= 2, f"{sid} cohort only spans {types}"
        assert types <= {"investor", "corporation", "university", "research_institution"}

    # A4: no dead/failed jobs — the whole flow drained cleanly.
    stuck = await store.pool.fetchval(
        "SELECT count(*) FROM jobs WHERE status IN ('failed','dead')")
    assert stuck == 0

    # A4 (API surface): endpoints return the shapes the dashboard reads.
    import httpx
    from api import app as api_app
    # api/app.py:47 `_pool(app)` returns `app.state.store.pool` — inject the Store,
    # NOT a bare pool. Drive the ASGI app in-loop via httpx.ASGITransport rather than
    # the sync TestClient: TestClient runs the app in a separate thread/event loop, but
    # the injected Store's asyncpg pool is bound to THIS test's loop — asyncpg
    # connections cannot cross event loops. ASGITransport runs the app on the current
    # loop (so the shared pool works) and does NOT fire api/app.py:31 `lifespan` (which
    # would Store.connect() against the dev DATABASE_URL and repoint app.state.store at
    # the WRONG database).
    api_app.app.state.store = store               # point the API at the harness DB
    transport = httpx.ASGITransport(app=api_app.app)  # no lifespan → injected store kept
    async with httpx.AsyncClient(transport=transport, base_url="http://ns") as client:
        assert len((await client.get("/entities")).json()) == fixtures.ENTITY_COUNT
        body = (await client.get(f"/matches?startup_id={startup_ids[0]}")).json()
        assert len(body) == 5


from spine import config
from tests.harness.replay_launcher import always_reject_verify


async def test_verify_reject_exhausts_budget_then_dead_letters(ns_store):
    """Drives the on_reject retry → dead-letter path the happy-path gate never touches.
    Pins the retry budget to config.MAX_ATTEMPTS — a regression in app.yaml's on_reject
    `max` (e.g. back to 2) fails here."""
    store = ns_store
    startup_ids = await fixtures.seed_and_enqueue_onboarding(store)
    await _drain(store)                                  # onboarding
    await fixtures.enqueue_outreach(store, startup_ids)

    # verify ALWAYS rejects → reject_and_rearm → on_reject budget → dead_letter
    launcher = ReplayLauncher(overrides={"verify": always_reject_verify})
    await Supervisor(store, launcher=launcher, reclaim_interval=0.2).run(drain=True)

    sid = startup_ids[0]
    saga_id = f"outreach:{sid}"

    # never verified → no match reaches draft_ready (stays 'ranked')
    draft_ready = await store.pool.fetchval(
        "SELECT count(*) FROM matches WHERE startup_id=$1 AND status='draft_ready'", sid)
    assert draft_ready == 0

    # the draft sub-jobs dead-lettered at exactly MAX_ATTEMPTS (retry budget honored)
    draft_jobs = await store.pool.fetch(
        "SELECT status, attempts FROM jobs WHERE saga_id=$1 AND stage='draft'", saga_id)
    assert draft_jobs, "expected per-partner draft sub-jobs"
    for r in draft_jobs:
        assert r["status"] == "dead", f"draft not dead-lettered: {dict(r)}"
        assert r["attempts"] == config.MAX_ATTEMPTS, (
            f"draft attempts={r['attempts']}, expected MAX_ATTEMPTS={config.MAX_ATTEMPTS} "
            "— on_reject `max` drifted from the retry budget")

    # a dead-letter milestone was recorded, and the drain terminated (no infinite retry)
    dl = await store.pool.fetchval(
        "SELECT count(*) FROM events WHERE saga_id=$1 AND kind LIKE '%DeadLetter%'", saga_id)
    assert dl >= 1
