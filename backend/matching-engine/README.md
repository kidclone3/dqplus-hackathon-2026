# Matching Engine

Matches founders and investors via pgvector similarity plus attribute
scoring (sector/stage/region), and proxies the ranked composite match list
from the Python matcher in `ai-data-platform/`.

Stack: FastAPI, `asyncpg` (raw Postgres + pgvector), `httpx` (proxy calls).

## Run

```bash
uv sync
uv run uvicorn app.main:app --reload --port 3002   # http://localhost:3002
```

## Configuration

Copy `.env.example` to `.env`:

| Var | Purpose |
|---|---|
| `PORT` | Bind port (default `3002`) |
| `DB_HOST`, `DB_PORT`, `DB_NAME`, `DB_USER`, `DB_PASSWORD`, `DB_SSL` | Postgres connection |
| `MATCH_VECTOR_WEIGHT`, `MATCH_ATTR_WEIGHT` | Blend of vector similarity vs. attribute score |
| `MATCH_CANDIDATE_POOL` | Candidate pool size before scoring/truncation |
| `MATCHING_API_URL` | Python matching API (uvicorn, `ai-data-platform/`) that owns the ranked `/matches` list |

## Endpoints

- `GET /matches` — forwarded as-is (query string included) to the Python
  matching API's `/matches`; this is what `dqplus.ddns.net/api/matches`
  resolves to behind nginx.
- `GET /matches/founders/:userId/investors` — local pgvector + attribute
  scoring, query params `limit`, `sector`, `stage`, `region`
- `GET /matches/investors/:userId/founders` — same, reversed roles
- `GET /health` — `{"status":"ok","db":"connected"}` or 503 `{"status":"degraded","db":"unavailable"}`

## Structure

- `app/main.py` — FastAPI app, lifespan (DB pool), `/health`, error handlers
- `app/routers/matches.py` — the three routes above
- `app/services/matching.py` — candidate lookup + scoring orchestration
- `app/services/scoring.py` — vector + attribute scoring blend
- `app/config.py` — env-driven configuration
- `app/db.py` — asyncpg pool

## Tests

```bash
uv run pytest tests/e2e --json-report --json-report-file=tests/artifacts/test_results.json -v
```

See `tests/README.md` for the coverage matrix. Runs against a real
Postgres + pgvector instance — no DB mocking.
