# VietNexus — System Roadmap

Where the product is, and where it goes next — across the web frontend, the backend
services, and the AI Data Platform. Component detail lives in the per-area roadmaps:

- [`docs/roadmap/frontend.md`](roadmap/frontend.md) — web + mobile clients
- [`docs/roadmap/backend.md`](roadmap/backend.md) — gateway, extract agent, matching path
- [`ai-data-platform/docs/ROADMAP.md`](../ai-data-platform/docs/ROADMAP.md) — spine, agents, RAG/GraphRAG

For how the system works *today*, see [`ARCHITECTURE.md`](ARCHITECTURE.md).

---

## Where we are (July 2026 — Phase 0, shipped)

The core loop is live end-to-end at **https://dqplus.ddns.net**:

- Register → onboarding profile → extraction (`extracted_profiles` + embedding) →
  ranked matches with human-readable reasons → client-side outreach draft.
- The legacy Node matching-engine is **retired**; `/matches` is served by the AI Data
  Platform's RAG matcher (pgvector KNN over the entity corpus + rule-based attribute
  scoring), preserving the app's 404 → extract → retry contract.
- Admin role (DB-provisioned only) gates the platform dashboard; data endpoints stay public.
- Everything runs in one Docker Compose stack (pgvector Postgres, gateway, extract,
  matching-api, web) with zero-downtime rolling web deploys behind a proxy container.
- E2E pytest suites per service against a real pgvector database; no mocking.

## Known debt carried out of the hackathon

These are the honest gaps the phases below exist to close:

| Gap | Where |
|-----|-------|
| Customers / partners / talent match intents have **no backend** (tabs show a "not connected" notice) | frontend + platform |
| Outreach drafts are a **client-side template** (`lib/draft.js`) while the platform already has cited, fact-checked bilingual draft sagas | frontend + platform |
| Consent + draft-ready state live **only in `localStorage`** (`vn.profile.<username>`) | frontend + gateway |
| Mobile app (Expo) still runs on **mock data** | mobile |
| Without `OPENAI_API_KEY` (FPT cloud), embeddings fall back to **lexical feature-hash** — matching works but isn't semantic; `/extract/text` and `/extract/crawl` fail outright | backend + platform |
| Production is an **autossh tunnel off a WSL2 dev machine** — a laptop reboot takes the site down | deployment |
| No CI/CD; deploys are manual scripts | all |
| Auth is minimal: HS256 JWT, no refresh/rotation, no rate limiting, admin gate **fails open** when `JWT_SECRET` is empty (standalone-dev behavior) | gateway + platform |

## Phase 1 — Demo-hard (rest of Q3 2026)

Goal: nothing embarrassing can happen in front of a judge or pilot user.

1. **Semantic embeddings everywhere, consistently.** Provision the FPT key in every
   environment; enforce corpus/query embedder consistency (`multilingual-e5-large`,
   1024-dim) with a startup check instead of tribal knowledge.
2. **Wire real drafts.** Replace `lib/draft.js` output with the platform's bilingual,
   fact-checked draft endpoint; keep the template as offline fallback.
3. **Persist consent + draft state server-side** (gateway `profiles`), so a cleared
   browser doesn't lose user decisions.
4. **CI on every push**: lint + the existing per-service e2e suites against the
   throwaway pgvector container.
5. **Close the fail-open admin gate**: require `JWT_SECRET` in any non-dev boot.

## Phase 2 — Product (Q4 2026)

Goal: from "matching demo" to "Innovation OS" — the tabs stop apologizing.

1. **Partner-type matching backend** for customers / partners / talent intents — the
   platform's entity model already supports corporations, universities, and research
   institutions; expose intent-specific match routes and light the tabs up one by one.
2. **Mobile on real APIs**: point the Expo app at the same `/api/*` contract; retire
   `mockData.js`.
3. **Real hosting**: move the compose stack onto the VPS (or a cloud host) and delete
   the tunnel chain; keep `rolling-deploy.sh` semantics. Consolidate the two Postgres
   containers (5432/5433) into one.
4. **Auth hardening**: refresh tokens, rate limiting at the proxy, password reset.
5. **Feedback loop**: capture accept/pass/contacted outcomes on matches and store them —
   the training signal Phase 3 needs.

## Phase 3 — Scale & ecosystem (2027)

Goal: the platform earns the "OS" name.

- **Learning-to-rank**: use the Phase 2 outcome signal to tune (then learn) the
  vector/attribute weights per intent.
- **GraphRAG as a first-class ranking input**, not just an explorer view — relationship
  paths (co-investors, alumni networks, portfolio adjacency) feed match rationale.
- **Continuous enrichment**: scheduled crawl/enrich sagas keep the entity corpus fresh
  with cited sources; stale-fact expiry.
- **Multi-tenant / program mode**: accelerators and government programs (NIC) run their
  own cohorts on the same spine.
- **Vietnamese-first UX**: full vi/en localization of the clients (drafts are already
  bilingual).

## Sequencing rules

- Anything touching the live path ships behind the existing rolling-deploy flow.
- No phase starts on a component while its Phase 1 CI gate is red.
- Schema changes go through `ai-data-platform/migrations/` (platform schemas) or the
  gateway's idempotent DDL bootstrap (app tables) — never hand-run SQL on the live DB.
