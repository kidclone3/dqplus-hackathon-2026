# Extract Agent

Extracts structured founder/investor information from profile text and
stores embeddings in pgvector for the matching engine to query.

Stack: Express, OpenAI-compatible client, `pg` + `pgvector`.

## Run

```bash
npm install
npm run dev          # http://localhost:3001, --watch reload
npm test             # node --test
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

- `src/app.js` / `src/index.js` — Express app + entrypoint
- `test/extract.routes.test.js` — route tests
- `testSupport/testServer.js` — test harness

Called by `backend/gateway` (`EXTRACT_SERVICE_URL`) to enrich a profile
after it's created or updated.
