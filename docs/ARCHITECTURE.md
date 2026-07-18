# VietNexus — Architecture

How the system is put together: services, request flow, data model, and deployment.
For the *why* behind each technology choice, see [`TECHNOLOGY.md`](TECHNOLOGY.md).

---

## 1. System at a glance

```
                         ┌───────────────────────────────────────────┐
   Web (Vite/React) ─┐   │                 VPS nginx                  │
                     ├──▶│  TLS termination · path routing · tunnels  │
   Mobile (Expo)  ───┘   │           https://dqplus.ddns.net          │
                         └───────────────────────────────────────────┘
                                            │  /api/*
             ┌──────────────────────────────┼──────────────────────────────┐
             ▼                               ▼                               ▼
     ┌───────────────┐             ┌───────────────────┐          ┌───────────────────┐
     │   Gateway     │             │  Extract Agent    │          │  Matching Engine  │
     │  :3000        │             │  :3001 (:3003 loc)│          │  :3002            │
     │  auth+profiles│             │  attrs+embeddings │          │  vector+attr rank │
     └──────┬────────┘             └─────────┬─────────┘          └─────────┬─────────┘
            │  profiles                       │ extracted_profiles          │ reads
            ▼                                 ▼                             ▼
     ┌───────────────────────────────────────────────────────────────────────────────┐
     │           Postgres 16 + pgvector  (DB: dealflow · shared by all services)        │
     └───────────────────────────────────────────────────────────────────────────────┘
                                            ▲
                                            │  same DB
                    ┌───────────────────────┴────────────────────────┐
                    │   AI Data Platform (Python spine + agents)      │
                    │   FastAPI read API :8000 · supervisor · sagas   │
                    └─────────────────────────────────────────────────┘
```

Three Node/Express services own the app's live path; a Python spine (the AI Data Platform)
shares the same Postgres for research-grade, evidence-cited matchmaking. `nginx` on the VPS
is the single public entry point and routes by URL prefix.

## 2. Services

### 2.1 Gateway — `backend/gateway` (:3000)

The front door for identity and profile data.

- **Auth**: `POST /auth/register`, `POST /auth/login` (bcrypt + JWT), `GET /auth/me`.
- **Profiles** (JWT-protected): `POST /profiles`, `GET /profiles/:id`, `PATCH /profiles/:id`.
- **Health**: `GET /health` (checks DB connectivity).
- ORM: **Sequelize**. In non-production it runs `sync({ alter: true })` to keep the schema
  aligned. Swagger docs are wired via `swagger-jsdoc` / `swagger-ui-express`.
- Owns the `users` and `profiles` tables.

### 2.2 Extract Agent — `backend/agent/extract` (:3001 canonical, **:3003 on this machine**)

Turns a profile (or raw text / a crawled page) into a canonical attribute set plus an
embedding, and writes one row per user into `extracted_profiles`.

- `POST /extract/profile` — load a gateway profile by `userId`, map it to canonical
  attributes, run the pipeline, upsert the row. (This is what the app calls.)
- `POST /extract/text`, `POST /extract/crawl` — same pipeline from raw text / a URL.
- `GET /extracted/:userId` — fetch the stored extraction.
- **Extraction** uses an OpenAI-compatible chat model with a strict JSON-schema response
  (`founder.schema.js` / `investor.schema.js`) against the FPT-cloud endpoint.
- **Embedding** uses `text-embedding-3-small` (1536-dim). If `OPENAI_API_KEY` is unset, it
  falls back to a deterministic **feature-hash embedding** (L2-normalized bag-of-words) so
  cosine ranking still works on lexical overlap — the pipeline never hard-fails.
- On boot it self-initializes its schema (`db/init.js` → `schema.sql`): creates the
  `vector` extension, the `extracted_profiles` table, and an **HNSW** cosine index.

> **Port note:** `.env.example` pins `PORT=3001`, but on the dev machine Uptime Kuma
> occupies 3001, so it runs on **3003** locally. The vite proxy and nginx tunnels are
> configured for 3003 accordingly.

### 2.3 Matching Engine — `backend/matching-engine` (:3002)

Ranks the opposite side of the market for a given user.

- `GET /matches/founders/:userId/investors` and
  `GET /matches/investors/:userId/founders` — the app's two live routes. Return `404` if
  the user has no `extracted_profiles` row yet (the app then triggers extraction and
  retries).
- `GET /matches` — **proxied** to the Python matching API (`MATCHING_API_URL`, default
  `:8000`) for the composite research-grade list.
- **Algorithm** (`matching.service.js` + `scoring.js`):
  1. Pull the requester's embedding, then fetch the `CANDIDATE_POOL` (default 50) nearest
     rows of the target role by pgvector cosine distance (`<=>`), with optional
     sector/stage/region pre-filters on the JSONB attributes.
  2. Compute `vectorScore = 1 − cosine_distance`.
  3. Compute `attributeScore` from explainable rules: **sector overlap** (Jaccard, ×0.4),
     **stage match** (+0.3), **geography match / global** (+0.2), **check size fits ask**
     (+0.05–0.1). Each firing rule adds a human-readable reason.
  4. Final `score = 0.7 · vectorScore + 0.3 · attributeScore` (weights configurable via
     `MATCH_VECTOR_WEIGHT` / `MATCH_ATTR_WEIGHT`), sorted descending, sliced to `limit`.

### 2.4 AI Data Platform — `ai-data-platform/` (Python)

A deterministic supervisor (event-sourced sagas, leased jobs, retries, dead-letter) that
drives isolated `feynman` / `pi` agent runtimes over stdio JSON-RPC for enrichment,
extraction, ranking, drafting, and verification — every fact cited, every draft
fact-checked. Exposes a FastAPI **read API + dashboard** on `:8000`
(`/entities /matches /sagas /jobs /events`). Full detail lives in its own docs:
[`ai-data-platform/docs/ARCHITECTURE.md`](../ai-data-platform/docs/ARCHITECTURE.md) and
[`AGENT_FLOWS.md`](../ai-data-platform/docs/AGENT_FLOWS.md).

## 3. Request flow — "show me my matches"

```
1. User completes profile      → Gateway  POST /profiles            (row in `profiles`)
2. App requests matches        → Matching GET  /matches/.../investors
3.   no extraction yet? (404)  → Extract  POST /extract/profile     (row in `extracted_profiles`)
4. App retries matches         → Matching GET  /matches/.../investors → ranked list + reasons
5. User opens a match          → outreach draft generated (client-side template)
```

The frontend encodes exactly this in `App.jsx` / `lib/api.js`: on a `404` from the matching
engine it auto-calls extraction, then retries the match request once.

## 4. Data model

All services share **one Postgres database (`dealflow`)**.

**`users`** (gateway) — credentials + `role` (`founder` | `investor`), links to a profile.

**`profiles`** (gateway, Sequelize) — the structured onboarding form: `company_name`,
`stage`, `industry`, `where_you_operate`, `website[]`, `description_product`, contact,
and investor economics (`avg_initial_investment`, `annual_investment_count`,
`avg_holding_period`, `year_founded`, `num_of_employees`, …). UUID PK, `underscored`,
timestamped.

**`extracted_profiles`** (extract agent) — one row per user, the matching substrate:

| Column | Purpose |
|--------|---------|
| `user_id` (UUID, unique) | FK-by-convention to the gateway user |
| `role` | `founder` \| `investor` |
| `source` | `profile` \| `text` \| `crawler` |
| `attributes` (JSONB) | canonical, queryable attribute set |
| `embedding_text` | the text that was embedded |
| `embedding` (`vector(1536)`) | semantic vector, **HNSW cosine index** |

The AI Data Platform adds its own `core` / `orchestration` / `control_plane` schemas
(entities, sources with `source_url`, matches, sagas, jobs, events) via
`ai-data-platform/migrations/`.

## 5. Frontend & mobile

- **Web** (`frontend/`): Vite + React 18 + GSAP. No CORS on the backends — the dev/preview
  server and production nginx both **proxy `/api/*`** by prefix (`/api/backend` → gateway,
  `/api/agents` → extract, `/api/matches` → matching engine, `/api` → gateway fallback).
  Session (`vn.session`) and a per-user profile mirror live in `localStorage`.
- **Mobile** (`mobile/`): Expo / React Native (React Navigation, Google Fonts) mirroring
  the web screens (auth, profile form, matches, match detail). Currently backed by
  `src/data/mockData.js`.

## 6. Deployment

- **Public URL**: `https://dqplus.ddns.net`.
- **VPS** (`13.250.9.139`, Ubuntu): `nginx` terminates TLS and routes by prefix to
  **autossh reverse tunnels** from the dev machine (`192.168.0.79`):
  - `/` → `8443` → vite preview (`:5173`)
  - `/api/agents/`, `/api/extract/` → `5002` → extract agent (`:3003`)
  - `/api/matches/` → `5003` → matching engine (`:3002`)
  - `/api/backend/`, `/api/` fallback → `5000` → gateway (`:3000`)
- Production build uses `VITE_API_BASE=/api` (same-origin). Vite preview must allow the host
  (`allowedHosts: ['dqplus.ddns.net']`).
- **Local dev**: `./start.sh` boots Postgres (pgvector) via docker-compose, copies
  `.env.example → .env` where missing, and launches all three Node services with tailed
  logs into `logs/`.

**Operational notes**

- `docker-compose.yml` pins `pgvector/pgvector:pg16` so the `vector` extension is durable
  across container recreation (an earlier apt-installed pgvector in a sibling container was
  ephemeral).
- autossh tunnels must use an **absolute** key path with `-f`; a relative path breaks after
  daemonizing. The VPS sshd rate-limits rapid reconnects (~1–2 min lockout).
