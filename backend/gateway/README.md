# Gateway

REST API gateway fronting VietNexus: user auth and profile management. The
`frontend/` and `mobile/` clients talk to this service; it forwards match
requests to `matching-engine` and can call `agent/extract` for enrichment.

Stack: Express, Sequelize (Postgres), JWT auth, bcrypt, Swagger/OpenAPI docs.

## Run

```bash
npm install
npm run dev          # http://localhost:3000, --watch reload
```

Swagger UI is served per `src/config/swagger.js` (check console output on
boot for the exact path).

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

- `src/app.js` / `src/index.js` — Express app + entrypoint
- `src/routes/` — `auth.routes.js` (register/login), `profile.routes.js` (CRUD, authenticated), `matches.routes.js` (forward to the Python matching API)
- `src/services/` — `auth.service.js`, `profile.service.js`
- `src/middleware/` — `authenticate.js` (JWT), `authorize.js` (role checks), `errorHandler.js`
- `src/models/` — Sequelize models (`user.model.js`, `profile.model.js`)
- `src/config/` — `database.js` (Sequelize/Postgres), `swagger.js` (OpenAPI)

## Endpoints

- `POST /auth/register`, `POST /auth/login` — roles: `founder`, `investor`
- `/profiles` — authenticated CRUD, linked to the current user
- `GET /matches` — forwarded as-is (query string included, e.g. `?startup_id=...`) to
  the Python matching API's `/matches`
