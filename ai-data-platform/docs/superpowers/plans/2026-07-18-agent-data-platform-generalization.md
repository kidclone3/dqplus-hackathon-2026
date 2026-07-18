# Agent Data Platform Generalization — Implementation Plan

**Goal:** Extract every deal-flow assumption out of `spine/` into an app manifest + plugin module so one platform instance (`spindle/`) can host arbitrary apps, with the matchmaker as app #1 — proven by the A1–A5 North Star still passing, driven entirely through the manifest.

**Architecture:** The work is *extraction behind a passing regression gate*, not a rewrite. **Phase 0 builds that gate first**: a deterministic, offline A1–A5 harness that runs the real saga/lease/event machinery against an ephemeral Postgres with a **fake agent runtime** (`ReplayLauncher`) — no LLM, no web, ~0 cost, sub-second. Every subsequent extraction phase (1–6, per spec §G build order) must keep that harness green. Phases 1–6 are authored **just-in-time** — each phase's exact edits depend on the prior phase's landed code — but their file boundaries, the three resolved seam interfaces, and their acceptance gate are locked here.

**Tech Stack:** Python 3.12, `uv`, asyncpg, Postgres, pytest + pytest-asyncio, jsonschema, PyYAML, FastAPI/TestClient. Reference spec: `docs/superpowers/specs/2026-07-18-agent-data-platform-generalization-design.md`.

---

## Why Phase 0 exists (read before starting)

The spec's own risk mitigation (R-b) is *"do the extraction behind a passing A1–A5 regression test."* **That test does not exist.** The North Star (README "Acceptance run") was verified **manually** from a `docker compose down -v` cold boot driven by **live** feynman/pi agents making real web calls (~$1.67, minutes, non-deterministic). An autonomous extraction can neither run that nor use it as an oracle.

Phase 0 closes exactly that gap. The insight: `RuntimeLauncher` is **already** a `Protocol` (`spine/transport.py:283`) and `Supervisor.__init__` **already** accepts an injected `launcher` (`spine/supervisor.py:30`). So we can substitute a fake launcher that returns scripted, schema-valid agent JSON and run the entire cold-boot flow (`bootstrap → onboard-drain → outreach → outreach-drain → API assertions`) deterministically. That harness is the load-bearing safety net for Phases 1–6; it is also working, testable software on its own.

---

## Resolved seam decisions (these unblock Phases 1–6)

The spec (§C/§D) leaves three load-bearing seams under-specified. Locking them now so the JIT phase plans are unambiguous:

### Seam 1 — the agent-stage plugin contract (spec §C gap)
The manifest shows `@stage` only for *code* stages, but agent stages carry app logic too: **build prompt → validate result (R3 schema) → persist + advance**. Today these live in `sagas.build_prompt/validate/persist_and_advance` and `outreach.draft_prompt/verify_prompt/validate`. Lock the plugin contract as **one `AgentStage` handler per agent stage**, registered like ports:

```python
# spindle exposes these decorators to plugins; the supervisor calls the registered handler.
@agent_stage("enrich")
class EnrichStage(AgentStageHandler):
    async def build_prompt(self, ctx: StageCtx) -> str: ...
    def validate(self, data) -> bool: ...                       # R3 schema check
    async def persist_and_advance(self, ctx: StageCtx, data) -> None: ...
```

`StageCtx = {app_id, saga_id, subject_id, target_id, trace_id, store, attempts, port}`. The supervisor's generic `_dispatch` becomes: resolve `stage → {run, port?}` from the manifest; for `run: code` call the `@stage` fn; for `run: <agent>` run the pooled worker then hand `RpcResult.data` to the stage handler's `validate`/`persist_and_advance`. **`match`'s fan-out and `verify`'s retry are NOT special cases** — they are `persist_and_advance` implementations that call `store.complete_and_fanout` / `store.reject_and_rearm` (see Seam 2).

### Seam 2 — fan-out + `on_reject` as generic DAG primitives (spec §C/§D gap)
Today `_match_stage` fans out per-partner `draft` jobs and `_verify_stage` hand-rolls the reject→rearm→dead-letter loop. Generalize to two manifest-driven store primitives that already exist in spirit (`complete_and_fanout`, `reject_and_rearm`, `dead_letter`):
- **Fan-out:** a stage's `persist_and_advance` may return `next_jobs: list[{stage, target_id, agent}]`; the DAG engine enqueues them in the same transaction that completes the current job.
- **`on_reject: {retry: <stage>, max: N, then: dead}`:** a declarative retry edge the DAG engine reads from the manifest. When a handler signals rejection (returns `Reject(feedback=...)`), the engine rearms `<stage>`'s sub-job with feedback up to `max`, else dead-letters. Replaces the hand-written logic in `_verify_stage`.

### Seam 3 — the `Store` cleave (spec §B/§E gap)
`spine/store.py` interleaves **platform** methods (jobs/events/sagas/artifacts: `acquire_job`, `finish_stage`, `complete_and_fanout`, `reclaim_expired_leases`, `record_event`) with **app** methods (`upsert_entity`, `upsert_edge`, `upsert_match`, `set_match_draft`, `list_ready_partners`, `get_match`). Cleave into:
- `spindle/adapters/postgres_store.py` — **platform only**, every method gains an `app_id` param; the single-transaction `finish_stage`/`complete_and_fanout` write **only** queue+event+saga+artifact rows (never app tables). The `SKIP LOCKED` lease, `LISTEN/NOTIFY`, and one-transaction event+job+saga write are preserved verbatim — they are the crash-recovery story.
- `apps/matchmaker/store.py` — the app's own entity/edge/match accessors, called from `@stage`/`AgentStageHandler` bodies via `ctx.store` (app store), on the same pool.

**Invariant:** the platform transaction writes the generic `artifacts` row (blackboard); the app writes its `matches`/`entities` rows in the *handler*, before calling the platform advance. Order: app-write → platform advance-in-txn (idempotent on re-run per R6/R9).

These three decisions are the acceptance contract for the JIT phase plans; do not deviate without updating this section.

---

## File Structure

**Phase 0 (built in full below):**
- Create: `tests/harness/__init__.py` — harness package
- Create: `tests/harness/replay_launcher.py` — fake `RuntimeLauncher` + per-stage canned-response generators
- Create: `tests/harness/fixtures.py` — small deterministic seed (3 startups + 8 partners) + in-process bootstrap
- Create: `tests/harness/db.py` — ephemeral throwaway-database fixture (migrations applied)
- Create: `tests/test_north_star.py` — the A1–A5 assertions, driving the full cold-boot flow offline
- Modify: `pyproject.toml` — register the `north_star` marker (no new deps)

**Phases 1–6 (roadmap + gate locked here, code authored JIT):** see "Extraction Roadmap" at the end.

---

## Phase 0 — A1–A5 Deterministic Regression Harness

> Deliverable: `uv run pytest tests/test_north_star.py -v` runs the entire cold-boot flow offline against an ephemeral DB with a fake agent runtime and asserts A1–A5, in <5s, at $0 cost. This is the gate every later phase must keep green.

> **⛔ ULTRACODE / WORKFLOW EXECUTION CONSTRAINTS — read before orchestrating:**
> 1. **Only Phase 0 is workflow-drivable today.** Phases 1–6 are authored just-in-time and have no concrete edits or per-task oracles yet — a deterministic workflow cannot fan out or verify code it does not possess. Scope any workflow run to Phase 0.
> 2. **Tasks 0.1 → 0.5 are STRICTLY SEQUENTIAL, not a fan-out.** All five append to the *same* `tests/test_north_star.py` and build on the same `ns_store`/`fixtures`/`ReplayLauncher` state (0.4 needs 0.1+0.2+0.3 landed). Run them as a serial pipeline — parallel fan-out would clobber the shared file. The only genuinely parallel sub-step is Task 0.2's five per-stage schema checks.
> 3. **Iterate each task against its pytest gate — do not author-run-once.** The gate is "the named test PASSED (ran, not skipped)," verified per the runner note in Task 0.5. Loop the task's fix→run until green before advancing.
> 4. **Run pytest from the repo root.** `Supervisor.__init__` loads `agents/specs.yaml` via a CWD-relative path (`pools.DEFAULT_PATH`); a non-root CWD makes the harness fail to find agent specs.

### Task 0.1: Ephemeral throwaway-database fixture

**Files:**
- Create: `tests/harness/__init__.py`
- Create: `tests/harness/db.py`
- Test: `tests/test_north_star.py` (smoke portion first)

- [ ] **Step 1: Create the harness package marker**

`tests/harness/__init__.py`:
```python
"""Offline A1–A5 regression harness: fake agent runtime + ephemeral DB."""
```

- [ ] **Step 2: Write the ephemeral-database helper**

Rationale: the harness needs a *clean* DB (it runs migrations + a full drain). We create a uniquely-named throwaway database off the configured server, apply migrations into it, and drop it after. This never touches the dev DB and needs no schema juggling.

`tests/harness/db.py`:
```python
"""Ephemeral Postgres database for the North Star harness.

Creates a throwaway DB `dealflow_ns_<hex>` on the configured server, applies
migrations/*.sql into it, yields a Store bound to it, and drops it after. Skips
the whole harness if Postgres is unreachable (same policy as tests/conftest.py).
"""
from __future__ import annotations

import uuid
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit

import asyncpg

from spine import config
from spine.store import Store

MIGRATIONS_DIR = Path(__file__).resolve().parents[2] / "migrations"


def _swap_db(dsn: str, dbname: str) -> str:
    parts = urlsplit(dsn)
    return urlunsplit(parts._replace(path=f"/{dbname}"))


async def db_reachable() -> bool:
    try:
        conn = await asyncpg.connect(config.DATABASE_URL, timeout=3)
        await conn.close()
        return True
    except Exception:
        return False


async def create_ephemeral() -> tuple[str, Store]:
    """Returns (dbname, Store bound to a fresh migrated DB)."""
    dbname = f"dealflow_ns_{uuid.uuid4().hex[:12]}"
    admin = await asyncpg.connect(_swap_db(config.DATABASE_URL, "postgres"))
    try:
        await admin.execute(f'CREATE DATABASE "{dbname}"')
    finally:
        await admin.close()

    dsn = _swap_db(config.DATABASE_URL, dbname)
    conn = await asyncpg.connect(dsn)
    try:
        for path in sorted(MIGRATIONS_DIR.glob("*.sql")):
            await conn.execute(path.read_text())
    finally:
        await conn.close()

    store = await Store.connect(dsn, min_size=1, max_size=6)
    return dbname, store


async def drop_ephemeral(dbname: str, store: Store) -> None:
    await store.close()
    admin = await asyncpg.connect(_swap_db(config.DATABASE_URL, "postgres"))
    try:
        await admin.execute(
            "SELECT pg_terminate_backend(pid) FROM pg_stat_activity "
            "WHERE datname = $1 AND pid <> pg_backend_pid()", dbname)
        await admin.execute(f'DROP DATABASE IF EXISTS "{dbname}"')
    finally:
        await admin.close()
```

- [ ] **Step 3: Write a failing smoke test for the fixture**

`tests/test_north_star.py`:
```python
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
```

- [ ] **Step 4: Register the marker so pytest doesn't warn**

Modify `pyproject.toml` `[tool.pytest.ini_options]`, add:
```toml
markers = ["north_star: full offline A1–A5 cold-boot regression (needs Postgres)"]
```

- [ ] **Step 5: Run the smoke test**

Run: `docker compose up -d postgres && uv run pytest tests/test_north_star.py -v`
Expected: PASS (or SKIP if Postgres unreachable). Confirms migrations apply into a fresh DB and the Store binds.

- [ ] **Step 6: Commit**

```bash
git add tests/harness/__init__.py tests/harness/db.py tests/test_north_star.py pyproject.toml
git commit -m "[test] north-star harness: ephemeral migrated DB fixture

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

### Task 0.2: `ReplayLauncher` — the fake agent runtime

**Files:**
- Create: `tests/harness/replay_launcher.py`
- Test: `tests/test_north_star.py` (add launcher unit checks)

- [ ] **Step 1: Write the fake launcher + per-stage response generators**

Design: the fake keys its canned JSON by `spec.stage` and returns **schema-valid** data derived from the prompt, so it is target-agnostic and produces deterministic A1–A5 structure. `rank` echoes back exactly the `partner_id`s present in the prompt (descending composites) so `LlmJudgeMatcher` maps them 1:1. `verify` always passes (the happy-path North Star). Each generator returns data that passes the matching `schemas/*.json`.

`tests/harness/replay_launcher.py`:
```python
"""Fake RuntimeLauncher for the offline North Star harness.

Returns scripted, schema-valid agent JSON keyed by spec.stage so the full saga
machinery runs with no LLM/web/cost. Implements the RuntimeLauncher Protocol
(spine/transport.py:283): spawn(spec, worker_id[, on_usage]) -> RpcChannel-like.
"""
from __future__ import annotations

import re

from spine.transport import RpcResult, TurnUsage

_PARTNER_ID_RE = re.compile(r'"partner_id":\s*"([^"]+)"')


def _enrich(prompt: str) -> dict:
    # Provenance-shaped profile + one relationship (feeds edges → A2).
    return {
        "entity_type": "startup",
        "name": {"value": "Fixture Co", "source_url": "https://example.org/a", "confidence": "high"},
        "country": {"value": "VN", "source_url": "https://example.org/a", "confidence": "high"},
        "website": {"value": None, "confidence": "unavailable", "source_url": None},
        "relationships": [
            {"kind": "raised_from", "dst_name": "Seed Capital VN",
             "source_url": "https://example.org/round"},
        ],
        "collection_summary": {"sources_visited": 2},
    }


def _extract(prompt: str) -> dict:
    # Broad looking_for so investor + corporation + university all pass the
    # permissive filter → A3 cohort spans partner types.
    return {
        "sectors": ["ai"],
        "looking_for": ["funding", "corporate_pilot", "rd_collaboration"],
        "stage": "seed",
        "description_en": "Fixture startup building applied AI.",
        "description_vi": "Công ty khởi nghiệp AI ứng dụng.",
    }


def _rank(prompt: str) -> dict:
    ids = list(dict.fromkeys(_PARTNER_ID_RE.findall(prompt)))  # de-dup, keep order
    matches = []
    for i, pid in enumerate(ids):
        matches.append({
            "partner_id": pid,
            "composite": max(10, 95 - i * 5),
            "semantic": 0.8, "sector_overlap": 0.9,
            "rationale_en": f"Strong sector alignment with {pid}. Clear value; modest stage risk.",
            "rationale_vi": f"Phù hợp lĩnh vực với {pid}. Giá trị rõ ràng; rủi ro giai đoạn.",
        })
    return {"matches": matches}


def _draft(prompt: str) -> dict:
    return {
        "subject_en": "Introduction", "subject_vi": "Giới thiệu",
        "draft_en": "Hi — we think there is a strong fit worth exploring together.",
        "draft_vi": "Xin chào — chúng tôi thấy có sự phù hợp đáng để cùng khám phá.",
    }


def _verify(prompt: str) -> dict:
    return {"pass": True, "issues": [], "checks": {"grounded": True, "bilingual": True}}


STAGE_RESPONSES = {
    "enrich": _enrich, "extract": _extract,
    "match": _rank, "draft": _draft, "verify": _verify,
}


class ReplayChannel:
    def __init__(self, gen):
        self._gen = gen
        self._proc = None

    async def prompt(self, message: str, *, timeout: float = 300.0) -> RpcResult:
        return RpcResult(
            id=1, text="", data=self._gen(message),
            usages=[TurnUsage(tokens_in=0, tokens_out=0, cost_usd=0.0)],
            stop_reason="settled",
        )

    async def new_session(self) -> None:
        pass

    async def close(self) -> None:
        pass


class ReplayLauncher:
    """Deterministic fake: RpcResult.data is schema-valid canned JSON per stage."""

    def __init__(self):
        self.calls: list[str] = []

    async def spawn(self, spec, worker_id, on_usage=None) -> ReplayChannel:
        self.calls.append(spec.stage)
        gen = STAGE_RESPONSES.get(spec.stage)
        if gen is None:
            raise AssertionError(f"no canned response for stage {spec.stage!r}")
        return ReplayChannel(gen)
```

- [ ] **Step 2: Write a failing test that the canned outputs satisfy the R3 schemas**

Append to `tests/test_north_star.py`:
```python
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
```

- [ ] **Step 3: Run it**

Run: `uv run pytest tests/test_north_star.py -k canned_responses -v`
Expected: PASS for all 5 stages. If any fails, fix the generator to satisfy that schema (do not weaken the schema).

- [ ] **Step 4: Commit**

```bash
git add tests/harness/replay_launcher.py tests/test_north_star.py
git commit -m "[test] north-star harness: ReplayLauncher fake agent runtime

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

### Task 0.3: Deterministic fixture seed + in-process bootstrap

**Files:**
- Create: `tests/harness/fixtures.py`
- Test: `tests/test_north_star.py` (bootstrap-count assertion)

- [ ] **Step 1: Write the small fixture + bootstrap helper**

A minimal seed exercising all four partner types with guaranteed sector overlap (all `ai`), sized so counts are deterministic: 3 startups, 3 investors, 2 corporations, 2 universities, 1 research_institution = 11 entities, 8 partners (≥5 for `top_k`, cohort spans types → A3).

`tests/harness/fixtures.py`:
```python
"""Deterministic fixture seed + in-process bootstrap for the North Star harness.

Mirrors scripts/bootstrap.py's enqueue shape (one onboarding saga + enrich job per
entity) but in-process against an injected Store, using a tiny fixed seed so A1–A5
counts are deterministic.
"""
from __future__ import annotations

from spine.ids import entity_id

STARTUPS = [
    {"name": "Alpha AI", "sectors": ["ai"]},
    {"name": "Beta Robotics", "sectors": ["ai"]},
    {"name": "Gamma Health", "sectors": ["ai"]},
]
PARTNERS = [
    {"name": "Seed Capital VN", "type": "investor", "sectors": ["ai"]},
    {"name": "North Fund", "type": "investor", "sectors": ["ai"]},
    {"name": "Delta Ventures", "type": "investor", "sectors": ["ai"]},
    {"name": "MegaCorp", "type": "corporation", "sectors": ["ai"]},
    {"name": "IndusTech", "type": "corporation", "sectors": ["ai"]},
    {"name": "Hanoi University", "type": "university", "sectors": ["ai"]},
    {"name": "Danang Institute", "type": "university", "sectors": ["ai"]},
    {"name": "National Research Lab", "type": "research_institution", "sectors": ["ai"]},
]

STARTUP_COUNT = len(STARTUPS)
PARTNER_COUNT = len(PARTNERS)
ENTITY_COUNT = STARTUP_COUNT + PARTNER_COUNT


async def seed_and_enqueue_onboarding(store) -> list[str]:
    """Upsert entities (status='seeded') + one onboarding saga + enrich job each.
    Returns the startup ids. Idempotent (deterministic slug ids, ON CONFLICT)."""
    startup_ids: list[str] = []
    for rec in STARTUPS + PARTNERS:
        typ = rec.get("type", "startup")
        eid = entity_id(typ, rec["name"])
        await store.upsert_entity(eid, typ, rec["name"],
                                  profile={"sectors": rec["sectors"]}, status="seeded")
        saga_id = f"onboarding:{eid}"
        await store.create_saga(saga_id, "onboarding", eid, current_step="enrich")
        await store.enqueue_job(saga_id, "enrich", target_id=eid, agent="enricher")
        if typ == "startup":
            startup_ids.append(eid)
    return startup_ids


async def enqueue_outreach(store, startup_ids: list[str]) -> None:
    """Mirror scripts/outreach.py: one outreach saga + filter job per startup."""
    for sid in startup_ids:
        saga_id = f"outreach:{sid}"
        await store.create_saga(saga_id, "outreach", sid, current_step="filter")
        await store.enqueue_job(saga_id, "filter", target_id=sid, agent=None)
```

> NOTE at authoring time: confirm `store.upsert_entity`/`create_saga`/`enqueue_job` signatures against `spine/store.py` (they are `upsert_entity(id, type_, name, profile=, status=)`, `create_saga(saga_id, type_, subject_id, *, current_step=)`, `enqueue_job(saga_id, stage, *, target_id=, agent=)`). Adjust the calls if the real signatures differ from what's shown — the harness must use the *actual* store API, since it is the thing under test.

- [ ] **Step 2: Add a failing bootstrap-count test**

Append to `tests/test_north_star.py`:
```python
from tests.harness import fixtures


async def test_bootstrap_enqueues_one_enrich_per_entity(ns_store):
    startup_ids = await fixtures.seed_and_enqueue_onboarding(ns_store)
    assert len(startup_ids) == fixtures.STARTUP_COUNT
    n_entities = await ns_store.pool.fetchval("SELECT count(*) FROM entities")
    n_enrich = await ns_store.pool.fetchval(
        "SELECT count(*) FROM jobs WHERE stage='enrich' AND status='ready'")
    assert n_entities == fixtures.ENTITY_COUNT
    assert n_enrich == fixtures.ENTITY_COUNT
```

- [ ] **Step 3: Run it**

Run: `uv run pytest tests/test_north_star.py -k bootstrap_enqueues -v`
Expected: PASS. (If a store method name/signature differs, fix the fixture per the NOTE — do not change production code in Phase 0.)

- [ ] **Step 4: Commit**

```bash
git add tests/harness/fixtures.py tests/test_north_star.py
git commit -m "[test] north-star harness: deterministic fixture seed + bootstrap

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

### Task 0.4: The A1–A5 assertions (full offline cold-boot)

**Files:**
- Modify: `tests/test_north_star.py`

- [ ] **Step 1: Write the failing end-to-end North Star test**

Drives the *real* `Supervisor` with the fake launcher injected, through both saga drains, then asserts A1–A5 structurally. Uses `Supervisor(..., launcher=ReplayLauncher())` and `run(drain=True)`.

Append to `tests/test_north_star.py`:
```python
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

    # A2: relationship edges were written from enrich relationships.
    edges = await store.pool.fetchval("SELECT count(*) FROM edges")
    assert edges >= fixtures.ENTITY_COUNT           # ≥1 relationship per entity

    # A3: each startup has 5 verified bilingual draft_ready matches spanning types.
    for sid in startup_ids:
        n = await store.pool.fetchval(
            "SELECT count(*) FROM matches WHERE startup_id=$1 AND status='draft_ready' "
            "AND draft_en IS NOT NULL AND draft_vi IS NOT NULL", sid)
        assert n == 5, f"{sid} has {n} draft_ready matches, expected 5"
        types = await store.pool.fetch(
            "SELECT DISTINCT e.type FROM matches m JOIN entities e ON e.id=m.partner_id "
            "WHERE m.startup_id=$1 AND m.status='draft_ready'", sid)
        assert {r["type"] for r in types} & {"investor", "corporation", "university"}

    # A4: no dead/failed jobs — the whole flow drained cleanly.
    stuck = await store.pool.fetchval(
        "SELECT count(*) FROM jobs WHERE status IN ('failed','dead')")
    assert stuck == 0

    # A4 (API surface): endpoints return the shapes the dashboard reads.
    from fastapi.testclient import TestClient
    from api import app as api_app
    # api/app.py:47 `_pool(app)` returns `app.state.store.pool` — inject the Store,
    # NOT a bare pool. And do NOT use `with TestClient(...)`: the context manager
    # fires api/app.py:31 `lifespan`, which calls Store.connect() against the dev
    # DATABASE_URL and overwrites app.state.store → assertions would then run against
    # the WRONG database. Plain (non-context-manager) TestClient never runs lifespan.
    api_app.app.state.store = store               # point the API at the harness DB
    client = TestClient(api_app.app)              # no `with` — lifespan must not fire
    assert len(client.get("/entities").json()) == fixtures.ENTITY_COUNT
    body = client.get(f"/matches?startup_id={startup_ids[0]}").json()
    assert len(body) == 5
```

> VERIFIED against `api/app.py`: `_pool(app)` returns `app.state.store.pool` (`api/app.py:47`) and `lifespan` (`api/app.py:31`) connects `Store.connect()` to the **dev** `DATABASE_URL`. Both facts are load-bearing: inject the **Store** (`app.state.store = store`), and use a **plain** `TestClient` — a `with TestClient(...)` block runs lifespan and silently repoints the API at the dev DB, so the `== ENTITY_COUNT` / `== 5` assertions would pass or fail on dev-DB contents. The assertion intent (dev's 57 → harness `ENTITY_COUNT`, 5 matches) is fixed.

- [ ] **Step 2: Run it (expect real failures to fix)**

Run: `uv run pytest tests/test_north_star.py::test_north_star_a1_through_a5 -v`
Expected initially: FAIL. Likely first failures and their meaning:
- **Timeout / hangs:** `run(drain=True)` needs the drain monitor to see zero ready/leased jobs. Confirm `Supervisor._all_stages` covers all fixture stages (it unions onboarding + outreach). If the fake resolves instantly, the drain should complete within a couple reclaim ticks.
- **`match` count ≠ 5:** the fixture must present ≥5 candidates past `filter`; all partners share sector `ai`, so all 8 pass → `top_k` (config `MATCH_TOP_K`, default 5). If `MATCH_TOP_K` ≠ 5, assert against `config.MATCH_TOP_K` instead of the literal 5.
- **`edges` = 0:** confirm `link` writes edges from `enrichment["relationships"]`; the fake `_enrich` includes one relationship, so each entity yields ≥1 edge.

Fix the **harness** (fixture sizing, response shape) until green — Phase 0 changes no production code.

- [ ] **Step 3: Confirm determinism**

Run 3×: `uv run pytest tests/test_north_star.py::test_north_star_a1_through_a5 -v --count=1` (or rerun the command three times). Expected: PASS every time, identical counts. If flaky, the drain is racing — increase determinism by draining until `jobs` has zero `ready|leased` rows before asserting (the test already drains via `run(drain=True)`; add an explicit post-drain assertion that no jobs remain `ready|leased`).

- [ ] **Step 4: Commit**

```bash
git add tests/test_north_star.py
git commit -m "[test] north-star: full offline A1-A5 cold-boot regression gate

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

### Task 0.5: Make the gate runnable as one command + document it

**Files:**
- Modify: `README.md` (Tests section)
- Create: `scripts/north_star.sh` (convenience runner)

- [ ] **Step 1: Add a one-line runner**

`scripts/north_star.sh`:
```bash
#!/usr/bin/env bash
# Offline A1–A5 regression gate. Needs a reachable Postgres (docker compose up -d postgres).
set -euo pipefail
docker compose up -d postgres >/dev/null
# REQUIRE_DB=1 turns a down/misconfigured Postgres into a FAILURE, not a SKIP, so the
# gate can never go green without actually running the A1–A5 flow end-to-end.
# --strict-markers + -ra surfaces any skip; a gate run must show PASSED, never skipped.
NORTH_STAR_REQUIRE_DB=1 exec uv run pytest tests/test_north_star.py -v -ra \
  --strict-markers -m north_star
```

> **Workflow-execution note:** an ultracode workflow driving this gate must verify the
> run actually **executed** (non-zero `passed`, zero `skipped`) — not merely "pytest exit
> 0". A SKIP is *not* green. With `NORTH_STAR_REQUIRE_DB=1` the fixture converts an
> unreachable DB into a failure, so a clean exit already implies the flow ran; still,
> assert `skipped == 0` from the `-ra` summary as belt-and-suspenders.

- [ ] **Step 2: Document it under README "Tests"**

Add after the existing pytest block:
```markdown
### Offline North Star gate

`bash scripts/north_star.sh` runs the full A1–A5 cold-boot flow **offline** (fake agent
runtime, ephemeral DB, ~0 cost, <5s). This is the regression gate for the platform
generalization: every extraction phase must keep it green.
```

- [ ] **Step 3: Run the gate via the script**

Run: `bash scripts/north_star.sh`
Expected: PASS. This is the green baseline Phases 1–6 must preserve.

- [ ] **Step 4: Commit**

```bash
chmod +x scripts/north_star.sh
git add scripts/north_star.sh README.md
git commit -m "[test] north-star: one-command offline gate + docs

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

**Phase 0 exit criteria:** `bash scripts/north_star.sh` is green and deterministic across 3 runs. This is the oracle for everything below.

---

## Extraction Roadmap (Phases 1–6)

> These follow spec §G build order. Each is authored as its own bite-sized plan **just-in-time**, immediately before execution, because each phase's exact line-level edits depend on the prior phase's landed code — writing them now would be speculative fiction that violates the no-placeholder rule. What is **locked here** for each: the files touched, the resolved interface (from "Resolved seam decisions"), and the non-negotiable acceptance gate.
>
> **Universal gate for every phase 1–6:** `bash scripts/north_star.sh` stays green, plus the existing `uv run pytest -q` suite stays green. A phase is not done until both pass. Point the North Star harness at the *new* code path as it moves (e.g. once the manifest loader exists, the harness drives the manifest path).

### Phase 1 — Platform migrations (`app_id`, `apps` table)
- **Files:** Create `migrations/004_platform_appid.sql` (add `app_id` to `jobs`/`events`/`saga_instances`/`artifacts`, backfill `'matchmaker'`, add `apps` table, widen unique keys to `(app_id, saga_id, …)`). Modify nothing in Python yet.
- **Gate:** migrations apply cleanly into the ephemeral DB; harness still green (it applies `migrations/*.sql`, so the new column must default/backfill so existing store methods keep working before they learn `app_id`).
- **Watch:** unique-constraint changes (`UNIQUE(app_id, saga_id, stage)`) — the harness's idempotency assumptions depend on these.

### Phase 2 — Manifest schema + loader + plugin/port registry (pure, no DB)
- **Files:** Create `spindle/manifest/schema.json`, `spindle/manifest/loader.py`, `spindle/registry.py` (the `@stage`/`@port`/`@agent_stage` decorators from Seam 1). Create `apps/matchmaker/app.yaml` mirroring today's two sagas (§C example).
- **Gate:** pure unit tests (no DB) — loading `app.yaml` yields the same stage lists as today's hardcoded `ONBOARDING_STAGES`/`OUTREACH_STAGES`; harness unaffected (still on the old path).

### Phase 3 — Extract `core/` behind `ports.py`; `Store` cleave (Seam 3)
- **Files:** Create `spindle/core/` (saga engine, DAG advance, reconciler — no I/O imports), `spindle/ports.py`, `spindle/adapters/postgres_store.py` (platform-only, `app_id` params), `apps/matchmaker/store.py` (app tables). Add the `core/` import-lint (`spindle/core` may not import `adapters`/`asyncpg`) as a test.
- **Gate:** highest-risk phase. Harness green throughout — run it after *each* method migration. The single-transaction `finish_stage`/`complete_and_fanout` semantics must be preserved exactly (R5/R6). Keep the old `spine.store.Store` as a thin shim delegating to the split stores until Phase 5 removes it, so the harness never breaks mid-cleave.

### Phase 4 — Generalize scheduler / DAG / pool-manager to read the manifest (spec §D)
- **Files:** Modify `spine/supervisor.py` → `spindle/app/supervisor.py`: replace the `_dispatch` if/elif over stage names with manifest resolution `stage → {run, port?}` (Seam 1); replace `_NEXT`/hardcoded fan-out with the DAG engine reading the saga list + `on_reject` edge (Seam 2); key pools by `(runtime, skill, model)` with load-time tool/model compatibility validation (risk R-a). 
- **Gate:** the harness now drives the **fully generic** supervisor over the manifest. Green = the four §D changes preserved behavior. This is where "zero deal-flow strings in the platform core" becomes checkable — grep `spindle/` for `enrich|extract|draft|matcher|startup` should be empty.

### Phase 5 — Move matchmaker into `apps/matchmaker/` (manifest + plugin + migrations)
- **Files:** Move `spine/sagas.py`+`spine/outreach.py` bodies → `apps/matchmaker/plugin.py` (`@stage` for `ingest`/`link`/`filter`; `@agent_stage` handlers for `enrich`/`extract`/`match`/`draft`/`verify` per Seam 1). Move `spine/matcher/` → `apps/matchmaker/` behind `@port("matcher")`. Move `entities`/`edges`/`matches` DDL → `apps/matchmaker/migrations/`. Delete the old `spine.store.Store` shim.
- **Gate:** harness green — but now update `tests/harness/fixtures.py` to bootstrap via the manifest loader + `app_id='matchmaker'`, and the `ReplayLauncher` unchanged (it is app-agnostic — it fakes runtimes, not domain logic). This proves the fake seam survives the extraction.

### Phase 6 — Regression proof
- **Files:** none new. Run `bash scripts/north_star.sh` (offline) **and** the full live cold-boot from the README (`docker compose down -v` → 6 commands) to confirm A1–A5 with real agents through the manifest path.
- **Gate:** offline harness green + one live cold-boot pass (manual, budget ~$1.67) + `grep -rE 'enrich|extract|draft|startup|matcher|dealflow' spindle/` returns nothing. That is the spec's definition of done.

---

## Self-Review notes (Phase 0)

- **Spec coverage:** Phase 0 implements the missing R-b precondition end-to-end; Phases 1–6 map 1:1 onto spec §G build order and the three §C/§D/§E gaps are resolved in "Resolved seam decisions."
- **No production changes in Phase 0** — it only adds `tests/harness/*`, `tests/test_north_star.py`, a marker, a script, and README docs. This keeps the gate trustworthy: it exercises today's code unchanged, so any red in Phases 1–6 is a genuine regression, not harness drift.
- **Type/API consistency:** the harness calls the *real* store/supervisor/transport APIs (`Store.connect(dsn,…)`, `Supervisor(store, launcher=…)`, `RpcResult`, `TurnUsage`, `AgentSpec.stage`) verified against `spine/`.

### Ultracode-readiness review outcome (subagent pass)

Verified against real code and **confirmed correct** (do not re-check): `ReplayLauncher.spawn(spec, worker_id, on_usage=None)` matches `_run_worker`'s call site (`supervisor.py:147`) and the Protocol (`transport.py:283`); `RpcResult(stop_reason="settled")` ⇒ `success==True`; `Store.connect(dsn, …)` takes a positional DSN; `Supervisor(store, launcher=…, reclaim_interval=…)` kwargs match; fixture store calls match real signatures (NOTE-1 needs no change); `run(drain=True)` terminates via `_drain_monitor` over `_all_stages`; `config.MATCH_TOP_K==5` and `MATCH_MAX_CANDIDATES==8` ⇒ A3 `==5` holds; `ONBOARDING_STAGES` has no `ingest` so the fixture correctly starts at `enrich`; A2 edges (11 ≥ ENTITY_COUNT) and A3 cohort intersection both hold.

Fixed after review: (1) API pool injection was wrong (`app.state.pool` → `app.state.store`) + lifespan/dev-DB trap — Task 0.4 now correct and its NOTE upgraded to VERIFIED; (2) skip-vacuity — the gate now fails (not skips) when Postgres is down via `NORTH_STAR_REQUIRE_DB`; (3) Phase-0 serial constraint + Phase-0-only workflow scope + repo-root CWD now stated in the ⛔ banner.

Remaining non-blocking gaps (accept or harden at authoring time):
- `db.py` runs `CREATE DATABASE` against the `postgres` maintenance DB as the configured role — needs CREATEDB privilege; if the role lacks it the gate fails cleanly (acceptable) but the message won't distinguish it from "PG down."
- `_rank`'s `"partner_id"` regex also matches the OUTPUT example inside `build_rank_prompt` (`llm_judge.py:77`); harmless today (`LlmJudgeMatcher` drops out-of-set ids via `by_id`), but add a comment so a future prompt-format edit doesn't silently change fixture counts.
- Task 0.4 Step 3 mentions `--count=1` (pytest-repeat, not a dep) — use plain reruns; the plan already hedges to "rerun 3×."
```

