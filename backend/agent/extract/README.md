# Extract Agent

Extracts structured founder/investor information from profile text and
stores embeddings in pgvector for the matching engine to query.

Stack: FastAPI, OpenAI-compatible client (`openai`), `asyncpg` + pgvector.

## Run

```bash
uv sync
uv run uvicorn app.main:app --reload --port 3001   # http://localhost:3001
uv run pytest tests/e2e                            # requires Postgres (see below)
```

`test-curl.sh` has example requests against a running instance.

## Configuration

Copy `.env.example` to `.env`:

| Var | Purpose |
|---|---|
| `PORT` | Bind port (default `3001`) |
| `DB_HOST`, `DB_PORT`, `DB_NAME`, `DB_USER`, `DB_PASSWORD`, `DB_SSL` | Postgres connection |
| `OPENAI_API_KEY` | API key for the chat/embedding provider — **never commit this**; keep it in `.env`/vault only |
| `OPENAI_BASE_URL` | OpenAI-compatible endpoint (defaults to an FPT Cloud marketplace gateway, not api.openai.com) |
| `OPENAI_CHAT_MODEL` | Extraction model (default `gpt-4o-mini`) |
| `OPENAI_EMBEDDING_MODEL`, `EMBEDDING_DIM` | Embedding model + vector dimension (default `text-embedding-3-small`, 1536) |

## Structure

- `app/main.py` — FastAPI app, lifespan (DB pool + schema init), health check, error handlers
- `app/config.py` — env-driven settings
- `app/db/` — asyncpg pool + `schema.sql` (run on startup)
- `app/routers/extract.py` — `/extract/*` and `/extracted/{userId}` routes
- `app/services/` — extraction (LLM), embedding (LLM or local feature-hash fallback), profile_source (maps gateway `profiles` rows to attributes), store (upsert/read `extracted_profiles`)
- `app/schemas/` — founder/investor JSON schemas for structured LLM output
- `tests/e2e/` — pytest end-to-end suite against a real Postgres (no DB/LLM mocking); see `tests/README.md`

Called by `backend/gateway` (`EXTRACT_SERVICE_URL`) to enrich a profile
after it's created or updated.
