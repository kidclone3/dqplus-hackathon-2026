# Matching Engine

Matches founders and investors via pgvector similarity plus attribute
scoring (sector/stage/region), and proxies the ranked composite match list
from the Python matcher in `ai-data-platform/`.

Stack: Express, `pg` (raw Postgres + pgvector).

## Run

```bash
npm install
npm run dev          # http://localhost:3002, --watch reload
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

## Structure

- `src/routes/match.routes.js` — the three routes above
- `src/services/matching.service.js` — candidate lookup + scoring orchestration
- `src/services/scoring.js` — vector + attribute scoring blend
- `src/config/db.js` — Postgres pool
