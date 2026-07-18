# Gateway

REST API gateway fronting VietNexus: user auth and profile management. The
`frontend/` and `mobile/` clients talk to this service; it forwards match
requests to `matching-engine` and can call `agent/extract` for enrichment.

Stack: FastAPI, asyncpg (Postgres), JWT auth, bcrypt, OpenAPI docs.

## Run

```bash
uv sync
uv run uvicorn app.main:app --port 3000 --reload
```

Docs are served at `/docs`.

## Configuration

Copy `.env.example` to `.env`:

| Var | Purpose |
|---|---|
| `PORT`, `HOST` | Bind address (default `3000`) |
| `CORS_ORIGIN` | Comma-separated allowed origins |
| `DB_HOST`, `DB_PORT`, `DB_NAME`, `DB_USER`, `DB_PASSWORD`, `DB_SSL` | Postgres connection |
| `JWT_SECRET`, `JWT_EXPIRES_IN` | Auth token signing |
| `EXTRACT_SERVICE_URL` | Base URL of `backend/agent/extract` |
| `MATCHING_API_URL` | Python matching API (uvicorn, `ai-data-platform/`) that owns the ranked `/matches` list |

## Structure

- `app/main.py` — FastAPI app, CORS, exception handlers, lifespan (DB pool + schema bootstrap), `/health`
- `app/routers/` — `auth.py` (register/login/me), `profiles.py` (CRUD, authenticated), `matches.py` (forward to the Python matching API)
- `app/services/` — `auth_service.py`, `profile_service.py`
- `app/deps.py` — JWT auth dependency, JSON body parsing
- `app/security.py` — bcrypt hashing, JWT issue/decode
- `app/db.py` — asyncpg pool + idempotent DDL bootstrap (replaces `sequelize.sync`)
- `app/config.py` — env vars

## Endpoints

- `POST /auth/register`, `POST /auth/login`, `GET /auth/me` — roles: `founder`, `investor` (an `admin` role exists in the DB but is provisioned only by a direct DB write, never through `/auth/register`)
- `/profiles` — authenticated CRUD, linked to the current user
- `GET /matches` — forwarded as-is (query string included, e.g. `?startup_id=...`) to
  the Python matching API's `/matches`

## Tests

Real Postgres, no DB mocking. See `tests/README.md` for the AC/BR/EF coverage
matrix.

```bash
uv run pytest tests/e2e --json-report --json-report-file=tests/artifacts/test_results.json -v
```
