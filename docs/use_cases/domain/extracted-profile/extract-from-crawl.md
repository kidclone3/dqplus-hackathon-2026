# DUC-EXTRACT-CRAWL — Extract From Crawl

> **Type:** Domain Use Case (DUC)
> **Service:** Extract agent (FastAPI port), port 3003
> **Endpoint:** `POST /extract/crawl`
> **Source of truth:** `backend/agent/extract/src/routes/extract.routes.js`,
> `backend/agent/extract/src/services/extraction.service.js`
> **Realizes:** [BUC-MATCHING](../../business/startup-investor-matching.md) (AF3 — manual extraction from crawled content)

## 1. Description

Extracts structured attributes from crawled web content (using the chat model), optionally
merges caller-supplied `metadata` over the extracted attributes, embeds, and upserts the
`extracted_profiles` row (source `"crawler"`, with `source_url`).

## 2. Actors

- **Crawler / integration** (unauthenticated service endpoint).
- **Extract agent**, **LLM (chat API)**, **Postgres** (`extracted_profiles`).

## 3. Preconditions

- `OPENAI_API_KEY` configured — the chat model is required (same as text extraction; EF3).

## 4. Request

`POST /extract/crawl`, JSON body:

| Field | Type | Required | Notes |
|-------|------|----------|-------|
| `userId` | string (uuid) | yes | Row key. |
| `role` | string | yes | `founder` or `investor`. |
| `url` | string | yes | Stored as `source_url`. |
| `content` | string | yes | Crawled text to extract from. |
| `metadata` | object | no | If an object, shallow-merged **over** the extracted attributes. |

## 5. Main Flow

```mermaid
flowchart TD
    A[POST /extract/crawl] --> B{userId, role, url, content present?}
    B -- no --> E1[400 userId, role, url and content are required]
    B -- yes --> C{role in founder|investor?}
    C -- no --> E2[400 role must be one of]
    C -- yes --> D[chat completion over content with role schema]
    D --> F{metadata is object?}
    F -- yes --> G[attributes = {...extracted, ...metadata}]
    F -- no --> H[attributes = extracted]
    G --> I[embed + UPSERT source=crawler, source_url=url]
    H --> I
    I --> J[201 record]
```

1. Validate `userId`, `role`, `url`, and `content` are present.
2. Validate `role ∈ {founder, investor}`.
3. Extract attributes from `content` via the chat model + role schema.
4. If `metadata` is an object, shallow-merge it over the extracted attributes (metadata wins).
5. Embed the attributes' text and upsert `extracted_profiles` with `source: "crawler"` and
   `source_url: url`.
6. Return `201` with the stored record.

## 6. Alternative Flows

- **AF1 — With `metadata`:** Supplied `metadata` keys override the LLM-extracted values for
  those keys.
- **AF2 — Re-extraction:** Overwrites any existing row for `userId` (upsert on unique `user_id`).

## 7. Exception Flows

- **EF1** Missing any of `userId`/`role`/`url`/`content` →
  `400 {"error": "userId, role, url and content are required"}`.
- **EF2** `role` not in `founder|investor` → `400 {"error": "role must be one of: founder, investor"}`.
- **EF3** `OPENAI_API_KEY` unset / provider auth failure → chat call fails (no keyless fallback
  for attribute extraction), surfaced via the error handler.

## 8. Business Rules

- **BR1** Same strict role-specific schema and normalization as [Extract from text](extract-from-text.md).
- **BR2** `metadata` (when an object) is shallow-merged **over** the extracted attributes.
- **BR3** The stored row records `source: "crawler"` and `source_url` = the request `url`.
- **BR4** Requires the chat model; no keyless fallback for attribute extraction.

## 9. Acceptance Criteria

- **AC1** With a valid key, valid input returns `201` with `source: "crawler"`, `source_url`
  echoing the request `url`, and role-schema attributes.
- **AC2** Supplying `metadata` overrides the corresponding extracted attribute values (AF1).
- **AC3** Missing any required field returns EF1's exact 400 payload.
- **AC4** An invalid `role` returns EF2's exact 400 payload.
- **AC5** With `OPENAI_API_KEY` unset, the request fails at the chat-model call (EF3).

## 10. Cross-References

- Text variant: [Extract from text](extract-from-text.md); deterministic variant:
  [Extract from profile](extract-from-profile.md).
- Read via: [Get extracted profile](get-extracted-profile.md); consumed by:
  [Find matches](../matching/find-matches.md).
