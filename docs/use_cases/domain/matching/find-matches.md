# DUC-MATCH-FIND — Find Matches

> **Type:** Domain Use Case (DUC)
> **Service:** Matching engine (FastAPI port), port 3002
> **Endpoints:**
> - `GET /matches/founders/{userId}/investors` — founder → ranked investors
> - `GET /matches/investors/{userId}/founders` — investor → ranked founders
> - `GET /matches` — bare passthrough proxy to the Python matching API (see §11)
> **Source of truth:** `backend/matching-engine/src/routes/match.routes.js`,
> `backend/matching-engine/src/services/matching.service.js`,
> `backend/matching-engine/src/services/scoring.js`
> **Realizes:** [BUC-MATCHING](../../business/startup-investor-matching.md) (step 4)

## 1. Description

Given a user's id, returns a ranked list of counterpart matches. The user's own extracted
profile is loaded, the nearest counterpart candidates are retrieved by pgvector cosine
distance, and each candidate is scored by a weighted blend of vector similarity and
role-specific attribute overlap.

## 2. Actors

- **Client** (frontend / gateway; the matching engine itself is unauthenticated).
- **Matching engine**, **Postgres** (`extracted_profiles`, pgvector).

## 3. Preconditions

- The requesting `userId` has an `extracted_profiles` row (BR1 / EF1).
- Counterpart profiles with embeddings exist to rank.

## 4. Request

Path param `userId`. Query params:

| Param | Default | Notes |
|-------|---------|-------|
| `limit` | 10 | Coerced to a number; clamped to `[1, 50]`. |
| `sector` | — | Optional pre-filter (lowercased). |
| `stage` | — | Optional pre-filter (lowercased). |
| `region` | — | Optional pre-filter (lowercased). |

Target role is fixed by the route: `.../investors` → `targetRole=investor`;
`.../founders` → `targetRole=founder`.

## 5. Main Flow

```mermaid
flowchart TD
    A[GET /matches/&lt;role&gt;/:userId/&lt;counterpart&gt;] --> B[SELECT me role, attributes]
    B --> C{extracted profile exists?}
    C -- no --> E1[404 No extracted profile for user]
    C -- yes --> D[build candidate query: role=target, user_id != me, optional filters]
    D --> F[pgvector: ORDER BY embedding <=> me.embedding LIMIT candidate_pool]
    F --> G[per candidate: vectorScore = 1 - cosine_distance]
    G --> H[attributeScore + reasons via scoring rules]
    H --> I[score = 0.7*vector + 0.3*attribute]
    I --> J[sort desc, slice to limit]
    J --> K[200 {userId, role, matches[]}]
```

1. Load `role, attributes` for `userId`; if none, `404`.
2. Build the candidate SQL: `ep.role = targetRole`, `ep.user_id <> userId`, plus any provided
   `sector`/`stage`/`region` filters (applied against role-appropriate JSONB keys, §8/BR4).
3. Retrieve up to `MATCH_CANDIDATE_POOL` (default 50) nearest candidates ordered by cosine
   distance; `vectorScore = 1 - (embedding <=> me.embedding)`.
4. For each candidate compute `attributeScore` and human-readable `reasons` (§6).
5. `score = round(0.7 * vectorScore + 0.3 * attributeScore, 4)` (weights configurable).
6. Sort by `score` descending and slice to `limit`.
7. Return `{ userId, role, matches: [...] }`.

**Success response — 200:**
```json
{ "userId": "<uuid>", "role": "founder",
  "matches": [
    { "userId": "<uuid>", "score": 0.8123, "vectorScore": 0.7912,
      "attributeScore": 0.86, "attributes": { ... },
      "reasons": ["sector overlap: fintech", "stage match: seed"] }
  ] }
```

## 6. Attribute Scoring (from `scoring.js`)

Scoring is always computed founder-attrs vs investor-attrs regardless of who requested
(the requester's role selects which side is the founder). Components (capped at 1.0):

| Component | Weight | Rule |
|-----------|--------|------|
| Sector | `0.4 × jaccard` | Jaccard overlap of founder `industry` vs investor `sectors`. |
| Stage | `0.3` | Founder `stage` is contained in investor `stages` (case-insensitive). |
| Geography | `0.2` | Investor `geographies` includes `global` (with any founder region), else region∩geo overlap. |
| Check size | `0.1` or `0.05` | Founder `funding_ask_usd` within investor `[check_size_min, check_size_max]`; `0.1` when both bounds present, else `0.05`. |

Each satisfied component appends a `reasons` string.

## 7. Exception Flows

- **EF1** No extracted profile for `userId` →
  `404 {"error": "No extracted profile for user; run extraction first"}`. This is the
  BUC-MATCHING EF1 loop: the client should trigger extraction and retry.
- **EF2** No counterpart candidates found → `200` with `matches: []` (empty, not an error).

## 8. Business Rules

- **BR1** Matching requires the requester's `extracted_profiles` row; it never reads `profiles`
  directly.
- **BR2** A user is never matched to themselves (`ep.user_id <> userId`) nor to their own role
  (`ep.role = targetRole`, the opposite role).
- **BR3** `limit` is clamped to `[1, 50]`; the candidate pool retrieved before scoring is
  `MATCH_CANDIDATE_POOL` (default 50).
- **BR4** Filters map to role-specific JSONB keys: for investors,
  `sectors`/`stages`/`geographies` (array containment `?`); for founders, `industry`
  (array containment) / `stage` (scalar equality `->>`) / `target_regions` (array containment).
  Filter values are lowercased before matching.
- **BR5** Composite weighting is `0.7` vector + `0.3` attribute (env: `MATCH_VECTOR_WEIGHT`,
  `MATCH_ATTR_WEIGHT`), rounded to 4 decimals; results sorted descending by composite.
- **BR6** The matching engine has no authentication of its own.

## 9. Acceptance Criteria

- **AC1** `GET /matches/founders/{userId}/investors` for a founder with an extracted profile
  returns `200 {userId, role: "founder", matches}` where every match has an investor's
  attributes, and results are sorted by descending `score`.
- **AC2** `GET /matches/investors/{userId}/founders` symmetrically returns founder matches.
- **AC3** A `userId` with no extracted profile returns EF1's exact 404 payload.
- **AC4** `limit=100` is clamped to at most 50 results; `limit=0` yields at least 1.
- **AC5** Each returned match's `score` equals `round(0.7*vectorScore + 0.3*attributeScore, 4)`.
- **AC6** Providing `sector`/`stage`/`region` restricts candidates to those matching the
  role-appropriate JSONB key (BR4).
- **AC7** A valid user with no counterparts returns `200` with `matches: []` (EF2).

## 10. Cross-References

- Data produced by: [Extract from profile](../extracted-profile/extract-from-profile.md),
  [Extract from text](../extracted-profile/extract-from-text.md),
  [Extract from crawl](../extracted-profile/extract-from-crawl.md).
- Prerequisite check surfaced to users in: [BUC-MATCHING](../../business/startup-investor-matching.md) EF1.

## 11. Note — bare `GET /matches` proxy

The matching engine also exposes a bare `GET /matches` that forwards the request (including the
query string, e.g. `?startup_id=...`) to the Python matching API (ai-data-platform, port 8000),
returning that upstream's status, content-type, and body verbatim (8s timeout). This is a
transparent passthrough to the [ai-data-platform `/matches`](../../../../ai-data-platform/api/app.py)
composite list and is distinct from the two role-scoped endpoints above. The gateway exposes an
equivalent passthrough at its own `GET /matches`. Behavior to preserve: pass query string
through unchanged; relay upstream status/body; on upstream/timeout failure the request errors
via the standard error handler.
