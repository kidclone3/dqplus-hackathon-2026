# BUC-MATCHING — Startup ↔ Investor Matching

> **Type:** Business Use Case (BUC)
> **System:** VietNexus rebuilt backend (FastAPI port of the Node/Express services)
> **Status:** Behavioral spec — 1:1 preservation of current Node behavior
> **Scope:** End-to-end journey a founder or investor takes from account creation to seeing ranked counterpart matches.

## 1. Summary

A founder or investor registers, creates a single company/firm profile, and the system
automatically derives a structured, embedded "extracted profile" from that data. Once
extracted, the user can request a ranked list of counterpart matches (investors for a
founder, founders for an investor) scored by a blend of vector (embedding) similarity and
attribute overlap.

This BUC is realized by three domain services and orchestrates the following Domain Use
Cases (DUCs):

| Step | DUC | Doc |
|------|-----|-----|
| Create account | Register | [`../domain/user/register.md`](../domain/user/register.md) |
| Authenticate | Login | [`../domain/user/login.md`](../domain/user/login.md) |
| Confirm session | Get current user | [`../domain/user/get-current-user.md`](../domain/user/get-current-user.md) |
| Enter company/firm data | Create profile | [`../domain/profile/create-profile.md`](../domain/profile/create-profile.md) |
| Auto-derive structured attributes | Extract from profile | [`../domain/extracted-profile/extract-from-profile.md`](../domain/extracted-profile/extract-from-profile.md) |
| Revise data | Update profile | [`../domain/profile/update-profile.md`](../domain/profile/update-profile.md) |
| Inspect derived attributes | Get extracted profile | [`../domain/extracted-profile/get-extracted-profile.md`](../domain/extracted-profile/get-extracted-profile.md) |
| View ranked counterparts | Find matches | [`../domain/matching/find-matches.md`](../domain/matching/find-matches.md) |

The related BUC for operational oversight is
[`admin-dashboard-access.md`](admin-dashboard-access.md).

## 2. Actors

| Actor | Description |
|-------|-------------|
| **Founder** | End user with role `founder`; owns a startup company profile, seeks investors. |
| **Investor** | End user with role `investor`; owns a firm profile, seeks founders/startups. |
| **Gateway service** | FastAPI service (port 3000) — authentication, profile CRUD, matches proxy. |
| **Extract agent** | FastAPI service (port 3003) — derives `extracted_profiles` rows + embeddings. |
| **Matching engine** | FastAPI service (port 3002) — pgvector + attribute scoring over extracted profiles. |
| **Postgres (pgvector)** | Shared datastore for `users`, `profiles`, `extracted_profiles`. |

The Founder and Investor follow the same journey; the only difference is `role` and which
counterpart type is returned by matching.

## 3. Preconditions

- The three services are running and share one Postgres database with the `vector` extension.
- The gateway holds `JWT_SECRET` (HS256) and `EXTRACT_SERVICE_URL`.
- The matching engine can read `extracted_profiles`.
- The extract agent can read `users`/`profiles` and write `extracted_profiles`; embeddings
  use the OpenAI-compatible API when `OPENAI_API_KEY` is set, otherwise a deterministic
  keyless feature-hash fallback.

## 4. Main Flow (happy path)

```mermaid
sequenceDiagram
    actor U as Founder / Investor
    participant GW as Gateway (:3000)
    participant EX as Extract agent (:3003)
    participant ME as Matching engine (:3002)
    participant DB as Postgres (pgvector)

    U->>GW: POST /auth/register {username, password, role}
    GW->>DB: INSERT users (bcrypt password)
    GW-->>U: 201 {user, token (JWT)}

    U->>GW: POST /profiles {company_name, ...} (Bearer token)
    GW->>DB: INSERT profiles; UPDATE users.profile_id
    GW--)EX: POST /extract/profile {userId} (fire-and-forget)
    GW-->>U: 201 profile
    EX->>DB: SELECT users JOIN profiles
    EX->>EX: map attributes, build embedding text, embed
    EX->>DB: UPSERT extracted_profiles (ON CONFLICT user_id)

    U->>ME: GET /matches/founders/{userId}/investors
    ME->>DB: SELECT me; pgvector cosine over candidates
    ME->>ME: composite = 0.7*vector + 0.3*attribute
    ME-->>U: 200 {userId, role, matches[]}
```

**Steps:**

1. User registers with `username`, `password`, `role` (`founder`|`investor`). Gateway
   returns the sanitized user (no password) plus a signed JWT. → DUC *Register*.
2. User creates exactly one profile with at least `company_name`. Gateway links the profile
   to the user and fires a background extraction trigger. → DUC *Create profile*.
3. Extract agent maps the profile row to role-specific attributes, builds an embedding, and
   upserts an `extracted_profiles` row keyed by `user_id`. → DUC *Extract from profile*.
4. User requests matches for their `userId`. Matching engine loads the user's extracted
   profile, retrieves the nearest counterpart candidates by cosine distance, blends vector
   and attribute scores, and returns the ranked list. → DUC *Find matches*.

## 5. Alternative Flows

- **AF1 — Returning user:** User already has an account and skips registration, calling
  *Login* to obtain a fresh JWT before creating/viewing data.
- **AF2 — Profile revision:** User edits their profile via *Update profile*; this re-fires the
  extraction trigger, refreshing the `extracted_profiles` row (upsert) so subsequent matches
  reflect the change.
- **AF3 — Manual re-extraction from free text or a crawl:** Instead of (or in addition to)
  the profile-derived extraction, an operator/integration may submit raw text or crawled web
  content for the user via *Extract from text* / *Extract from crawl*, overwriting the same
  `extracted_profiles` row.
- **AF4 — Inspect extraction:** Before matching, the user (or an operator) reads the derived
  attributes via *Get extracted profile* to confirm extraction succeeded.

## 6. Exception Flows

- **EF1 — Matching before extraction completes:** Extraction is fire-and-forget, so a user may
  request matches before their `extracted_profiles` row exists. The matching engine returns
  `404 {"error": "No extracted profile for user; run extraction first"}`. The client is
  expected to trigger/await extraction and retry (this is the frontend's documented
  404 → auto-extract → retry loop).
- **EF2 — Duplicate profile:** A user who already has a linked profile receives
  `409 {"error": "User already has a profile"}` on a second create.
- **EF3 — Extraction requires a key (text/crawl only):** *Extract from text* and *Extract from
  crawl* call the chat model and fail without `OPENAI_API_KEY`. Profile-derived extraction is
  deterministic and does not require a key (embeddings fall back to feature-hash).

## 7. Business Rules

- **BR1 — One profile per user.** A user may own at most one profile; the profile is linked
  via `users.profile_id`.
- **BR2 — Extraction is the matching prerequisite.** Matching operates only on
  `extracted_profiles`, never directly on `profiles`. No extracted row ⇒ no matches (EF1).
- **BR3 — Extraction is idempotent per user.** `extracted_profiles` is upserted on
  `user_id` (unique), so re-extraction (profile edit, text, crawl) replaces the prior row.
- **BR4 — Counterpart selection by role.** Founders match to investors; investors match to
  founders. A user is never matched to their own role or to themselves.
- **BR5 — Composite score weighting.** `score = 0.7 * vectorScore + 0.3 * attributeScore`
  (configurable via env), rounded to 4 decimals, sorted descending.
- **BR6 — Extraction trigger is non-blocking.** Profile create/update returns success even if
  the extraction trigger fails or is not configured (`EXTRACT_SERVICE_URL` unset); failures
  are logged, not surfaced to the user.

## 8. Acceptance Criteria

- **AC1** A new founder or investor can register, create a profile, and (after extraction)
  receive a non-error ranked match list for their `userId`.
- **AC2** Creating a profile links it to the user and triggers extraction without blocking the
  create response.
- **AC3** After extraction, `GET /matches/founders/{userId}/investors` returns investors only,
  and `GET /matches/investors/{userId}/founders` returns founders only, each sorted by
  descending composite score.
- **AC4** Requesting matches before extraction yields the 404 "run extraction first" response,
  and a subsequent request after extraction succeeds (EF1 loop).
- **AC5** Editing the profile refreshes the extracted row so later match requests reflect the
  new data (AF2 / BR3).

## 9. Cross-References

- Operational counterpart: [BUC-ADMIN — Admin dashboard access](admin-dashboard-access.md)
- All step-level behavior, status codes, and error payloads are specified in the linked DUCs
  under [`../domain/`](../domain/).
