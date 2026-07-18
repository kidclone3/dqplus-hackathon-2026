# Phase 6 — Regression Proof

> Plan: `docs/superpowers/plans/2026-07-18-agent-data-platform-generalization.md` →
> "Extraction Roadmap → Phase 6 — Regression proof".
> Date run: 2026-07-18. Branch: `feat/spindle-platform`.

Phase 6 has **no new files**. It is the definition-of-done gate for the whole
spine → spindle extraction: prove the platform core carries zero deal-flow
strings and that the A1–A5 North Star still holds. This document records the
**offline** half (run here, automated, $0) and pins the exact **live** cold-boot
command sequence a human must run to close A1–A5 with real feynman/pi agents.

## Definition of done — offline half (verified this run)

| Gate | Command | Result |
|---|---|---|
| Offline A1–A5 regression, zero skips | `bash scripts/north_star.sh` | **8 passed, 0 skipped** in 3.97s |
| Full suite green | `uv run pytest -q` | **64 passed, 0 skipped, 0 failed** in 5.34s |
| Zero deal-flow strings in platform core | `grep -rEn 'enrich\|extract\|draft\|startup\|matcher\|dealflow\|onboarding\|outreach' spindle/ --include='*.py' \| grep -v '# '` | **no matches (empty)** |

Notes:
- The grep also returns empty for the plan's narrower set
  (`enrich|extract|draft|startup|matcher|dealflow`). The platform core in `spindle/`
  (`registry.py`, `ports.py`, `app/`, `core/`, `adapters/`, `manifest/`) holds no
  domain vocabulary — every stage name, saga shape, pool key and retry edge is read
  from the loaded app manifest (`apps/matchmaker/app.yaml`).
- `north_star.sh` runs with `NORTH_STAR_REQUIRE_DB=1 --strict-markers -m north_star`,
  so a down/misconfigured Postgres would **FAIL** (not skip) the gate — the 8 PASSED
  are genuine end-to-end runs of the offline cold-boot flow against ephemeral Postgres
  with the fake `ReplayLauncher` agent runtime.
- The live-path entrypoint `python -m spine.supervisor` is now a thin compat shim
  re-exporting the manifest-driven `spindle.app.supervisor` (Phase 4/§D). The README
  acceptance commands therefore drive the **generic manifest path**, not the old
  hardcoded reconciler.
- Two `InterfaceWarning`s (asyncpg notification listener released to pool) are
  pre-existing test-teardown noise, not failures.

## Definition of done — live half (MANUAL human follow-up, NOT run here)

Per the plan, the live cold-boot is a **manual** pass (budget ~$1.67, minutes,
non-deterministic, real web calls). It was intentionally **not** executed in this
autonomous run — no live feynman/pi agents, no web calls, no spend. A human runs
the sequence below (verbatim from README "Acceptance run (Phase 5 — cold-boot E2E)")
to close A1–A5 with real agents through the manifest path.

Prereqs: Docker + Docker Compose (Postgres 16); `OPENROUTER_API_KEY` (or configured
provider key) present in the environment; run from the repo root.

```bash
# 1. Clean Postgres — full wipe of the pgdata volume (true cold boot, R13)
docker compose down -v && docker compose up -d postgres

# 2. Migrate + seed 57 entities + enqueue one enrich per entity
uv run python scripts/bootstrap.py

# 3. Onboard: drain enrich -> extract -> link (real agents, manifest path)
MAX_CONCURRENCY=6 uv run python -m spine.supervisor --drain

# 4. Enqueue outreach sagas for all 25 startups
uv run python scripts/outreach.py --all

# 5. Advance outreach: drain filter -> match -> draft -> verify
MAX_CONCURRENCY=6 uv run python -m spine.supervisor --drain

# 6. Serve the dashboard / API for the A4 assertions
uv run uvicorn api.app:app --port 8000
```

### A1–A5 acceptance assertions (against the running API from step 6)

```bash
# A1 — every entity onboarded to a normalized, provenance-shaped profile
curl -s localhost:8000/entities | jq 'length'                 # expect 57
# A4 — endpoints return the shapes the dashboard reads
curl -s 'localhost:8000/matches?startup_id=startup:enfarm-agritech' | jq '.[0]'
# Cost budget (R14) — whole run should land near $1.67
curl -s localhost:8000/costs | jq
```

Expected live outcome (from README measured results, deepseek/deepseek-v4-flash):

- **A1** — 25 startups onboarded; ~23 with real `source_url` provenance,
  fields shaped `{value, source_url, confidence}`; unfound fields
  `confidence:"unavailable"` (sparse-footprint startups per R8).
- **A2** — 32 partners across all 4 types (20 investor / 7 corporation /
  4 university / 1 research) with provenance; ~654 relationship `edges`.
- **A3** — all 25 startups have 5 ranked + explained (EN/VI rationale) + verified
  bilingual drafts = 125 `draft_ready` matches; cohort spans
  investor/corporation/university.
- **A4** — `GET /entities` (57) → `GET /matches?startup_id=…` (scored, drafted)
  → dashboard drill-down.
- **A5** — the 6 commands above, from zero, with zero dead/failed jobs.

A single green pass of the above (zero dead/failed jobs, budget ~$1.67) closes the
live half of the Phase 6 gate and, with the offline half above, satisfies the spec's
full definition of done.
