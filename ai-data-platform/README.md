# Deal-flow Matchmaker

Agent data platform for deal-flow matchmaking (problem #135, VAIC 2026 · sponsor NIC).

A **deterministic Python spine** (supervisor + Postgres) owns storage, orchestration
(event-sourced sagas), a pluggable ranking `Matcher` port, and all I/O. The fuzzy work —
enrichment, extraction, match explanation, drafting, verification — runs inside isolated
**`feynman` / `pi`** agent runtimes driven over stdio JSON-RPC. See
`docs/superpowers/specs/2026-07-18-agent-data-platform-design.md` for the full design.

## Unique selling points

1. **AI matching you can trust — the exact, most-correct result.** Not "an AI guessed a
   list." Every match is grounded in a real, cited source (each fact carries the
   `source_url` an agent actually visited; unfound facts are marked `unavailable`, never
   invented), and every draft is fact-checked by a second agent that *rejects* anything
   hallucinated. The output is the correct match with the evidence to prove it.

2. **Storytelling: Vietnamese startups go to the world.** Each match ships a ready-to-send
   introduction in **both Vietnamese and English**, with a rationale that tells the
   startup's story to the right global partner — investor, corporation, university, or
   research institution. It turns a bare company name into a credible pitch that crosses
   the language and context gap between VN founders and the world.

## Documentation

- [`docs/OVERVIEW.md`](docs/OVERVIEW.md) — **start here** — plain-language "what is an AI agent data platform" and what this does
- [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) — layer map, components, data model, reliability & cost model
- [`docs/AGENT_FLOWS.md`](docs/AGENT_FLOWS.md) — the runtimes, the spine↔agent JSON contract, and both sagas end to end
- [`docs/DESIGN_SYSTEM.md`](docs/DESIGN_SYSTEM.md) — dashboard visual language (tokens, components, conventions)
- [`docs/superpowers/specs/2026-07-18-agent-data-platform-design.md`](docs/superpowers/specs/2026-07-18-agent-data-platform-design.md) — full design of record
- [`docs/superpowers/specs/2026-07-19-self-improvement-loop-design.md`](docs/superpowers/specs/2026-07-19-self-improvement-loop-design.md) — **self-improvement loop** — the gated, un-gameable self-evolution layer (P1/P2 proven offline)

## Prerequisites

- [`uv`](https://docs.astral.sh/uv/) (Python 3.12+)
- Docker + Docker Compose (Postgres 16)
- Host agent auth for the pooled runtimes: `~/.pi` and `~/.feynman` (a DeepSeek key —
  `deepseek/deepseek-v4-flash` is the pinned model). The transport lifts
  `DEEPSEEK_API_KEY` out of host auth if it isn't already exported.

Agent-driven stages cost real LLM calls. The supervisor is pinned to `deepseek-v4-flash`
with a global concurrency cap (`MAX_CONCURRENCY`) to bound spend.

## Configuration

Copy `.env.example` to `.env` and adjust:

| Var | Default | Purpose |
|-----|---------|---------|
| `DATABASE_URL` | `postgres://dealflow:dealflow@localhost:5432/dealflow` | Postgres DSN |
| `JWT_SECRET` | *(empty)* | When set, the dashboard (`GET /`) requires a gateway JWT with `role=admin` (via `?token=`, `Authorization: Bearer`, or the cookie it sets). Admins are provisioned only by direct DB update. Empty → dashboard open (standalone dev). |
| `AGENT_MODEL` | `deepseek/deepseek-v4-flash` | Pinned model (all agents) |
| `MAX_CONCURRENCY` | `4` | Global cap across agent pools |
| `AGENT_TIMEOUT` | `240` | Per-turn wall clock (seconds) |
| `LEASE_SECONDS` | `300` | Job lease window — **keep `> AGENT_TIMEOUT`** (R6) |
| `MAX_ATTEMPTS` | `3` | Retry budget before dead-letter (R5) |

## Quick start (cold boot from zero)

```bash
cp .env.example .env
uv sync

# 1. Postgres (migrations apply via initdb; bootstrap also runs an idempotent runner)
docker compose up -d postgres

# 2. Seed entities + create/enqueue onboarding sagas (idempotent — safe to re-run)
uv run python scripts/bootstrap.py                 # all seed types
#   or a targeted subset:  --types startup --limit 3   |   --names enfarm,Touchstone

# 3. Advance onboarding sagas (enrich -> extract -> link -> EntityReady).
#    --drain exits once the queue empties; omit it to run continuously.
uv run python -m spine.supervisor --drain

# 4. Trigger outreach for every onboarded startup (rule-filter -> match -> draft -> verify)
uv run python scripts/outreach.py --all            # or --startup startup:enfarm-agritech

# 5. Advance the outreach sagas
uv run python -m spine.supervisor --drain

# 6. API + live dashboard
uv run uvicorn api.app:app --port 8000             # dashboard at http://localhost:8000
```

`POST /runs` (`{"startup_id": ...}` or `{"all": true}`) only **enqueues** outreach sagas —
a supervisor must be running to actually advance them (the API never touches agents). The
dashboard polls every 3s, so a live `python -m spine.supervisor` run is watchable on screen.

The `api` service is also containerized (`docker compose up api` builds `api/Dockerfile`);
the supervisor and agent pools always run on the host via `LocalProcessLauncher`.

## Reset

```bash
docker compose down -v     # drops the pgdata volume — full wipe (R13)
```

## Dump & restore

`pg_dump` lives inside the Postgres container, so run it through Compose (no host
Postgres client needed). Restores cleanly anywhere (`--no-owner --no-privileges`):

```bash
# Dump schema + data to a timestamped file
docker compose exec -T postgres \
  pg_dump -U dealflow -d dealflow --no-owner --no-privileges > dump_dealflow_$(date +%Y%m%d_%H%M%S).sql

# Restore into a running (empty) database
docker compose exec -T postgres psql -U dealflow -d dealflow < dump_dealflow_*.sql
```

Dump files (`dump_*.sql`) are git-ignored — they are data artifacts, not source.

## Hardening & recovery (Phase 4)

The spine is a **reconciler**, not the record — Postgres holds desired + leased state.

- **Crash recovery** — a job is leased with an expiry (`LEASE_SECONDS`). A worker that
  dies mid-job never renews its lease; the reclaim loop requeues it (`status='ready'`,
  `leased_by=NULL`) and a replacement picks it up. `close()` SIGKILLs the whole child
  process group so a feynman shim's node child can't keep spending.
- **No double effects** — `UNIQUE(saga_id, step, target_id)` on `artifacts` (latest-wins
  upsert) means a reclaimed/double-run job cannot create a second row;
  `UNIQUE(saga_id, stage, target_id)` on `jobs` (R5) guards double-dispatch.
- **Idempotency** — deterministic entity slugs `{type}:{slug(name)}` (R9) make
  `bootstrap.py` and the `link` stage safe to re-run: no duplicate entities, sagas, jobs,
  or `edges`.
- **Dead-letter** — a retryable sub-job (draft/verify loop) that exhausts `MAX_ATTEMPTS`
  is marked `dead` and a `DraftDeadLettered` milestone is appended (R5).
- **Session hygiene** — pooled workers reset with `{"type":"new_session"}` between jobs
  (R7); the current supervisor goes further, spawning a fresh process per job (N=1) so
  warm context can't bleed across targets.

## Acceptance run (Phase 5 — cold-boot E2E)

The North Star (§9) was verified from a true cold boot (`docker compose down -v`) on the
full seed — 25 startups + 20 investors + 7 corporations + 4 universities + 1 research
institution (57 entities). Exact reproducible path (A5):

```bash
docker compose down -v && docker compose up -d postgres   # 1. clean Postgres
uv run python scripts/bootstrap.py                        # 2. migrate + seed 57 + enqueue
MAX_CONCURRENCY=6 uv run python -m spine.supervisor --drain   # 3. onboard (enrich→extract→link)
uv run python scripts/outreach.py --all                   # 4. enqueue outreach for 25 startups
MAX_CONCURRENCY=6 uv run python -m spine.supervisor --drain   # 5. filter→match→draft→verify
uv run uvicorn api.app:app --port 8000                    # 6. dashboard at http://localhost:8000
```

Measured results (deepseek/deepseek-v4-flash only, zero dead/failed jobs):

| North Star | Result |
|---|---|
| A1 | 25 startups onboarded; 23 with real `source_url` provenance, fields shaped `{value, source_url, confidence}`, unfound fields `confidence:"unavailable"` (2 sparse-footprint startups per R8) |
| A2 | 32 partners across all 4 types (20 investor / 7 corporation / 4 university / 1 research) with provenance; 654 relationship `edges` |
| A3 | All 25 startups have 5 ranked+explained (EN/VI rationale) + verified bilingual drafts = 125 `draft_ready` matches; cohort spans investor/corporation/university |
| A4 | `GET /entities` (57) → `GET /matches?startup_id=…` (scored, drafted) → dashboard drill-down |
| A5 | The 6 commands above, from zero |

**Cost budget (R14):** the entire run cost **$1.67** — ~$0.029 per onboarded entity,
~$0.013 per match (enrich/feynman dominates at $1.17; pi draft+verify+match ≈ $0.39).
Watch it live at `GET /costs`.

## Tests

```bash
docker compose up -d postgres      # tests need a reachable Postgres (else they skip)
uv run pytest -q
```

Crash-recovery, idempotency, dead-letter, and session-hygiene coverage lives in
`tests/test_crash_recovery.py` and `tests/test_idempotency.py`.

### Offline North Star gate

`bash scripts/north_star.sh` runs the full A1–A5 cold-boot flow **offline** (fake agent
runtime, ephemeral DB, ~0 cost, <5s). This is the regression gate for the platform
generalization: every extraction phase must keep it green.
