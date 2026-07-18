# VietNexus (Rising Nexus)

Innovation OS matching Vietnamese startups with investors, corporate partners,
universities, and research institutions — hackathon monorepo (dqplus-hackathon-2026).

A founder or investor registers, fills a profile, and gets back reasoning-ranked
matches with bilingual (VI/EN) fact-checked introduction drafts, grounded in
cited sources rather than guessed.

> Live: **https://dqplus.ddns.net**

## Documentation

- [`docs/OVERVIEW.md`](docs/OVERVIEW.md) — **start here** — plain-language overview of the problem, solution, and users (non-technical).
- [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) — services, request flow, data model, deployment.
- [`docs/TECHNOLOGY.md`](docs/TECHNOLOGY.md) — the stack, the design decisions, and config.
- [`docs/ROADMAP.md`](docs/ROADMAP.md) — where the product goes next (system-wide, with per-component roadmaps under `docs/roadmap/`).
- [`ai-data-platform/docs/`](ai-data-platform/docs/) — the research-grade Python agent platform.

## Repo layout

| Path | What it is | Stack |
|---|---|---|
| [`frontend/`](frontend/README.md) | Web app — auth, profile form, matches, match detail | Vite + React 18 + GSAP |
| [`mobile/`](mobile/README.md) | Companion mobile app (NFC profile card, matches) | Expo + React Native |
| [`backend/gateway/`](backend/gateway/README.md) | Auth + profile REST API, fronts the other services | FastAPI + asyncpg + Postgres |
| [`backend/matching-engine/`](backend/matching-engine/README.md) | pgvector similarity + attribute scoring; proxies to the Python matcher | FastAPI + asyncpg |
| [`backend/agent/extract/`](backend/agent/extract/README.md) | Extracts structured founder/investor info, stores embeddings | FastAPI + OpenAI + pgvector |
| [`backend/agent/crawler/`](backend/agent/crawler/README.md) | Source-crawling agent (scaffold, not yet implemented) | — |
| [`ai-data-platform/`](ai-data-platform/README.md) | Deal-flow matchmaker: sourced, cited, fact-checked matching pipeline + dashboard | Python (uv) + Postgres |
| `web/admin/`, `web/client/` | Reserved scaffolding, not yet built out | — |

`frontend/` and `ai-data-platform/` are the actively developed web app and matching
pipeline; `backend/*` is the Python (FastAPI) API layer the web/mobile clients talk to,
with `/matches` forwarded to the Python matching API in `ai-data-platform/`.

## Quick start

### Everything in Docker

```bash
docker compose up -d --build
```

Brings up the whole stack: `postgres` (pgvector), `gateway`, `matching-engine`,
`extract` agent, `matching-api` (the Python `ai-data-platform` API), and `web`
(nginx serving the Vite build and proxying `/api/*` to the backends).

| Service | URL |
|---|---|
| web (frontend + `/api` proxy) | http://localhost:5173 |
| gateway | http://localhost:3000 |
| matching engine | http://localhost:3002 |
| extract agent | http://localhost:3003 |
| matching API (Python) | http://localhost:8000 |
| postgres | localhost:5433 |

Ports and credentials come from `.env` (see `.env.example` — defaults are the
deal-flow-matchmaker credentials `dealflow`/`dealflow`; every host port is
overridable, e.g. `WEB_PORT`, `GATEWAY_PORT`). `OPENAI_API_KEY` is optional —
without it the extract agent uses deterministic feature-hash embeddings, so the
profile → match flow still works.

The `ai-data-platform/migrations` are applied automatically the first time the
`pgdata` volume is created; the gateway and extract agent create their own
tables at startup.

### Deploying updates to a live site (zero downtime)

The `web` service runs internal-only behind a small `proxy` (nginx) that owns
host port `5173` and load-balances across `web` replicas via Docker DNS. To ship
a frontend change **without dropping a single request**:

```bash
bash deploy/rolling-deploy.sh
```

It builds the new image, starts a second `web` replica alongside the running one,
waits for it to become healthy, then drains the old replica — the proxy always
has a healthy backend. Verified with an in-flight request probe (`ok=800 fail=0`).

- **Do not** run `docker compose up -d --build web` for a live update — a single
  container owns the port, so it stops before the new one binds (a few seconds of
  errors). Use the script.
- To change `deploy/proxy.conf`, apply it with `docker exec dqplus-proxy nginx -s reload`
  (zero downtime). Recreating the `proxy` container briefly drops port `5173`.

See [`docs/ARCHITECTURE.md` §6](docs/ARCHITECTURE.md#6-deployment) for the full topology.

### Hybrid: postgres in Docker, services on the host

Requires Docker (for Postgres/pgvector) and [`uv`](https://docs.astral.sh/uv/) (Python 3.12).

```bash
./start.sh
```

This copies `.env.example` → `.env` (root and each `backend/*` service, first run
only), brings up `postgres` (pgvector) via `docker compose`, installs deps on
first run, and starts the gateway, extract agent, and matching engine, tailing
their logs.

| Service | URL |
|---|---|
| gateway | http://localhost:3000 |
| extract agent | http://localhost:3001 |
| matching engine | http://localhost:3002 |

Then, in separate terminals:

```bash
cd frontend && npm install && npm run dev   # http://localhost:5173
cd mobile && npm install && npm start        # Expo dev tools
```

For the Python deal-flow matchmaker (agent-driven sourcing/matching pipeline
with its own dashboard), see [`ai-data-platform/README.md`](ai-data-platform/README.md).

## Configuration

Root `.env` (copied from `.env.example`) configures the shared Postgres
container (`DB_NAME`, `DB_USER`, `DB_PASSWORD`, `DB_PORT`). Each service under
`backend/*` has its own `.env.example` for service-specific settings (ports,
JWT secret, `OPENAI_API_KEY`, `MATCHING_API_URL`, etc.) — copy and fill in
before running standalone without `start.sh`.

## Notes

- Secrets (API keys, JWT secrets, DB passwords) belong in `.env` files, never
  committed — `.gitignore` already excludes `.env` and `logs/`.
- Match datasets in `frontend/` are currently static pending full integration
  with the matching engine / `ai-data-platform` pipeline.
