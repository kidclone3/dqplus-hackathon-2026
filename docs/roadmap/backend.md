# Backend Roadmap — gateway, extract agent, matching path

Component roadmap under the [system roadmap](../ROADMAP.md). Current stack: Python 3.12 /
FastAPI / asyncpg / uv, one shared pgvector Postgres. Service detail in
[`../ARCHITECTURE.md`](../ARCHITECTURE.md).

## Today

- **Gateway (:3000)** — auth (bcrypt + HS256 JWT) and profiles; idempotent DDL bootstrap
  owns `users` / `profiles`; `admin` role is DB-provisioned only and gates the platform
  dashboard.
- **Extract agent (:3003 local / :3001 canonical)** — profile/text/crawl → canonical
  attributes + embedding → `extracted_profiles` (HNSW cosine index). Keyless
  feature-hash fallback keeps profile extraction working without an FPT key; the
  chat-model paths (`/extract/text`, `/extract/crawl`) require the key.
- **Matching** — the Node matching-engine is retired (compose `profiles: ["disabled"]`);
  `/matches` is served by the AI Data Platform (:8000), which self-fetches the
  requester's `extracted_profiles` row and preserves the 404 → extract → retry contract.
- **Tests** — per-service e2e pytest suites against a throwaway pgvector container
  (`dqplus-test-postgres`, :5434).

## Phase 1 — Demo-hard

| Item | Definition of done |
|------|--------------------|
| Close the admin fail-open | Empty `JWT_SECRET` refuses to boot outside an explicit dev flag; documented in `.env.example` |
| Embedder consistency check | Extract agent + platform assert at startup that they share the same embedding model/dimension as the stored corpus; loud failure, not silently-empty matches |
| FPT key in every env | Key provisioned for compose + deploy; feature-hash fallback demoted to a logged degraded mode |
| CI | Lint + e2e suites run on every push; `tests/artifacts/test_results.json` published as the artifact |
| Delete dead code | Remove the retired `backend/matching-engine` source once nothing references it (it is already disabled in compose) |

## Phase 2 — Product

| Item | Definition of done |
|------|--------------------|
| Consent/draft state API | Gateway persists consent + draft-ready flags on `profiles`; PATCH surface consumed by the web client |
| Auth hardening | Refresh tokens with rotation, per-IP rate limiting at the proxy, password reset flow |
| Match feedback endpoint | Accept / pass / contacted events stored per (user, match) — the ranking signal for Phase 3 |
| Intent-aware extraction | Extraction schema grows customer/partner/talent-relevant attributes so the new intent routes have substrate |
| Postgres consolidation | Single pgvector Postgres; the legacy `deal-flow-matchmaker-postgres-1` container (holding host 5432) is retired after data verification |
| Real hosting | Compose stack runs on the VPS (or cloud); autossh tunnel chain deleted; health-checked deploys |

## Phase 3 — Scale & ecosystem

- **Observability**: structured logs shipped somewhere queryable, request tracing across
  gateway → extract → platform, `/metrics` on each service.
- **Async extraction**: extraction becomes a queued job (the platform's saga machinery
  already exists) so slow crawls never block a request thread.
- **Multi-tenancy**: org/cohort scoping on `users`/`profiles` for program mode.
- **API versioning**: freeze `/api/v1` before external consumers (mobile store builds,
  partner integrations) depend on the shapes.

## Standing constraints

- All schema changes to app tables go through the gateway's idempotent DDL bootstrap;
  platform schemas go through `ai-data-platform/migrations/`. No hand-run SQL on live.
- Keep the `{"error": ...}` envelope, Decimal-as-string, and JS-style timestamps — the
  clients and e2e suites pin these shapes.
- Container healthchecks hit `127.0.0.1`, never `localhost` (IPv6 gotcha), and `web`
  stays scalable (no `container_name`, no published ports).
