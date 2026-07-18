# VietNexus — Technology & Solution

The full stack, and the reasoning behind each choice. For how the pieces fit together,
see [`ARCHITECTURE.md`](ARCHITECTURE.md).

---

## 1. Stack at a glance

| Layer | Technology | Where |
|-------|-----------|-------|
| Web frontend | Vite 5, React 18, GSAP (animation) | `frontend/` |
| Mobile | Expo 54, React Native 0.81, React Navigation 7 | `mobile/` |
| API services | Python 3.12, FastAPI, `uv` | `backend/*` |
| Auth | JWT (`pyjwt`), `bcrypt` | `backend/gateway` |
| DB access | `asyncpg` (raw SQL, idempotent DDL bootstrap at startup) | `backend/*` |
| Database | PostgreSQL 16 + **pgvector** (HNSW) | `docker-compose.yml` |
| AI (extraction) | OpenAI-compatible chat, JSON-schema output | `backend/agent/extract` |
| AI (embeddings) | `text-embedding-3-small` (1536-dim) + keyless fallback | `backend/agent/extract` |
| LLM provider | **FPT Cloud** OpenAI-compatible API | `mkp-api.fptcloud.com` |
| AI Data Platform | Python 3.12, `uv`, FastAPI, asyncio, event-sourced sagas | `ai-data-platform/` |
| Agent runtimes | `feynman` / `pi` over stdio JSON-RPC, DeepSeek `deepseek-v4-flash` | `ai-data-platform/` |
| Edge / deploy | nginx (TLS + routing), autossh reverse tunnels, Docker Compose | VPS |

## 2. Why these choices

**PostgreSQL + pgvector — one store, two jobs.** The core insight of the product is that
matching is *both* semantic ("these two descriptions are about the same thing") *and*
structural ("this investor writes checks this size at this stage"). pgvector lets a single
Postgres hold the 1536-dim embeddings **and** the queryable JSONB attributes, so one SQL
query does approximate-nearest-neighbor (HNSW cosine) *and* attribute filtering. No
separate vector database, no sync problem, one source of truth shared by every service.

**A blended, explainable score — not a black box.** Ranking is
`0.7 · vector + 0.3 · attributes`. The vector half captures fuzzy fit; the attribute half
is a small set of transparent rules (sector Jaccard, stage, geography, check-size fit) that
each emit a plain-language reason. Founders and investors see *why* a match ranked where it
did — trust matters more than a marginally better opaque score. Weights and candidate-pool
size are env-tunable.

**Python/FastAPI, split by concern.** Three small services (identity, extraction, matching)
instead of one monolith: each has a single responsibility, its own `.env`, and can be
deployed/tunneled independently. FastAPI keeps them thin and readable — the interesting
logic is the SQL and the scoring, not the framework — and the whole stack (services +
`ai-data-platform`) now shares one language and toolchain (`uv`).

**FPT Cloud for LLM/embeddings.** An OpenAI-compatible endpoint hosted in-region — relevant
for a Vietnam-focused product (latency, data locality, and using a local cloud sponsor).
Because it's OpenAI-compatible, the standard `openai` SDK works unchanged via `baseURL`.

**A keyless embedding fallback — graceful degradation.** If no API key is present, the
extract agent computes a deterministic feature-hash embedding instead of hard-failing. The
matching pipeline stays functional (on lexical overlap rather than true semantics), so the
app is always demoable even without provider credentials. This is a deliberate resilience
choice for a hackathon/demo context.

**JSON-schema-constrained extraction.** The chat model is called with
`response_format: json_schema`, so extraction returns a validated attribute object rather
than free text that needs parsing — fewer failure modes downstream.

**Deterministic spine, isolated fuzzy agents (AI Data Platform).** Storage, orchestration,
retries, and I/O are plain deterministic Python; only the genuinely fuzzy work
(enrichment, drafting, verification) runs inside sandboxed agent runtimes over a strict
JSON-RPC contract. This makes the AI parts *testable and bounded* — event-sourced sagas,
leased jobs, retry budgets, dead-letter, and a global concurrency cap on spend — instead of
one unbounded agent loop. See
[`ai-data-platform/docs/ARCHITECTURE.md`](../ai-data-platform/docs/ARCHITECTURE.md).

**Vite + GSAP.** Fast dev/build for the web app; GSAP drives the onboarding motion that
makes the "Innovation OS" feel polished in a demo. Expo gives a shared React model for a
native mobile client from the same mental design.

**nginx + autossh tunnels.** The app runs on a dev machine behind NAT; nginx on a small VPS
provides a stable public HTTPS origin and reverse-tunnels each service by URL prefix. Cheap,
reproducible, and keeps all service ports off the public internet.

## 3. The solution, in one paragraph

VietNexus captures a startup's or investor's profile, uses an AI agent to normalize it into
canonical attributes plus a semantic embedding stored in Postgres/pgvector, and ranks the
opposite side of the market with a transparent blend of vector similarity and rule-based
attribute fit — returning not just a list but the *reasons* behind it. The research-grade
AI Data Platform extends this into evidence-cited, fact-checked introductions in Vietnamese
and English, so a Vietnamese founder's story reaches the right global partner with proof
attached. The result: **the correct match, explained and evidenced — not an AI's guess.**

## 4. Configuration reference

Each service reads its own `.env` (copied from `.env.example` by `start.sh`).

**Shared database** (`.env` at root and per service):
`DB_NAME=dealflow`, `DB_USER=dqplus`, `DB_PASSWORD=hackathondqplus`, `DB_PORT=5432`.

**Gateway** — `PORT=3000`, `JWT_SECRET`, `JWT_EXPIRES_IN=1d`, `CORS_ORIGIN`,
`EXTRACT_SERVICE_URL`.

**Extract agent** — `PORT=3001` (**3003 locally**), `OPENAI_API_KEY` (optional — enables
true semantic embeddings + chat extraction), `OPENAI_BASE_URL=https://mkp-api.fptcloud.com`,
`OPENAI_CHAT_MODEL=gpt-4o-mini`, `OPENAI_EMBEDDING_MODEL=text-embedding-3-small`,
`EMBEDDING_DIM=1536`.

**Matching engine** — `PORT=3002`, `MATCH_VECTOR_WEIGHT=0.7`, `MATCH_ATTR_WEIGHT=0.3`,
`MATCH_CANDIDATE_POOL=50`, `MATCHING_API_URL=http://localhost:8000` (Python API for
composite `/matches`).

**Frontend** — `VITE_API_BASE=/api` (prod, same-origin via nginx). Dev proxy targets:
`GATEWAY_URL`, `EXTRACT_URL`, `MATCHING_URL`.

**AI Data Platform** — `DATABASE_URL`, `AGENT_MODEL=deepseek/deepseek-v4-flash`,
`MAX_CONCURRENCY=4`, `AGENT_TIMEOUT=240`, `LEASE_SECONDS=300` (keep `> AGENT_TIMEOUT`),
`MAX_ATTEMPTS=3`.

## 5. Running it

```bash
# Everything (Postgres + all three backend services), with tailed logs:
./start.sh

# Individually (uv sync on first run):
cd backend/gateway         && uv run uvicorn app.main:app --port 3000 --reload
cd backend/agent/extract   && uv run uvicorn app.main:app --port 3001 --reload   # :3003 here
cd backend/matching-engine && uv run uvicorn app.main:app --port 3002 --reload
cd frontend                && npm run dev   # :5173

# AI Data Platform (Python):
cd ai-data-platform && uv sync && uv run <...>   # see its README
```

Endpoints: gateway `http://localhost:3000`, extract `http://localhost:3003`, matching
`http://localhost:3002`, web `http://localhost:5173`, Python read API/dashboard
`http://localhost:8000`.
