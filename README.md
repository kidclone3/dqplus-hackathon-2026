# VietNexus (Rising Nexus)

Innovation OS matching Vietnamese startups with investors, corporate partners,
universities, and research institutions — hackathon monorepo (dqplus-hackathon-2026).

A founder or investor registers, fills a profile, and gets back reasoning-ranked
matches with bilingual (VI/EN) fact-checked introduction drafts, grounded in
cited sources rather than guessed.

## Repo layout

| Path | What it is | Stack |
|---|---|---|
| [`frontend/`](frontend/README.md) | Web app — auth, profile form, matches, match detail | Vite + React 18 + GSAP |
| [`mobile/`](mobile/README.md) | Companion mobile app (NFC profile card, matches) | Expo + React Native |
| [`backend/gateway/`](backend/gateway/README.md) | Auth + profile REST API, fronts the other services | Express + Sequelize + Postgres |
| [`backend/matching-engine/`](backend/matching-engine/README.md) | pgvector similarity + attribute scoring; proxies to the Python matcher | Express + pg |
| [`backend/agent/extract/`](backend/agent/extract/README.md) | Extracts structured founder/investor info, stores embeddings | Express + OpenAI + pgvector |
| [`backend/agent/crawler/`](backend/agent/crawler/README.md) | Source-crawling agent (scaffold, not yet implemented) | — |
| [`ai-data-platform/`](ai-data-platform/README.md) | Deal-flow matchmaker: sourced, cited, fact-checked matching pipeline + dashboard | Python (uv) + Postgres |
| `web/admin/`, `web/client/` | Reserved scaffolding, not yet built out | — |

`frontend/` and `ai-data-platform/` are the actively developed web app and matching
pipeline; `backend/*` is the Node API layer the web/mobile clients talk to, with
`/matches` forwarded to the Python matching API in `ai-data-platform/`.

## Quick start

Requires Docker (for Postgres/pgvector) and Node.js.

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
