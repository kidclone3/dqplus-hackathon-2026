# DUC-EXTRACT-TEXT — Extract From Text

> **Type:** Domain Use Case (DUC)
> **Service:** Extract agent (FastAPI port), port 3003
> **Endpoint:** `POST /extract/text`
> **Source of truth:** `backend/agent/extract/src/routes/extract.routes.js`,
> `backend/agent/extract/src/services/extraction.service.js`,
> `backend/agent/extract/src/schemas/founder.schema.js`,
> `backend/agent/extract/src/schemas/investor.schema.js`
> **Realizes:** [BUC-MATCHING](../../business/startup-investor-matching.md) (AF3 — manual extraction)

## 1. Description

Extracts structured, role-specific attributes from a free-text description using the chat model
(JSON-schema-constrained), embeds the result, and upserts the `extracted_profiles` row for the
given user (source `"text"`).

## 2. Actors

- **Operator / integration** (unauthenticated service endpoint).
- **Extract agent**, **LLM (OpenAI-compatible chat API)**, **Postgres** (`extracted_profiles`).

## 3. Preconditions

- `OPENAI_API_KEY` (and base URL/model) configured — the chat model is required (BR2/EF3).

## 4. Request

`POST /extract/text`, JSON body:

| Field | Type | Required | Notes |
|-------|------|----------|-------|
| `userId` | string (uuid) | yes | Row key. |
| `role` | string | yes | `founder` or `investor` — selects the extraction schema. |
| `text` | string | yes | Free-text to extract from. |

## 5. Main Flow

```mermaid
flowchart TD
    A[POST /extract/text] --> B{userId, role, text present?}
    B -- no --> E1[400 userId, role and text are required]
    B -- yes --> C{role in founder|investor?}
    C -- no --> E2[400 role must be one of]
    C -- yes --> D[chat completion with role JSON schema]
    D --> F[parse structured attributes]
    F --> G[build embedding text + embed]
    G --> H[UPSERT extracted_profiles source=text]
    H --> I[201 record]
```

1. Validate `userId`, `role`, and `text` are present.
2. Validate `role ∈ {founder, investor}`.
3. Call the chat model with the system prompt and the role-specific strict JSON schema
   (`founder_profile` or `investor_profile`); parse the returned JSON.
4. Build the embedding text from the attributes and embed it.
5. Upsert `extracted_profiles` on `user_id` with `source: "text"`.
6. Return `201` with the stored record.

## 6. Alternative Flows

- **AF1 — Re-extraction:** Overwrites any existing row for `userId` (upsert on unique `user_id`).

## 7. Exception Flows

- **EF1** Missing any of `userId`/`role`/`text` → `400 {"error": "userId, role and text are required"}`.
- **EF2** `role` not in `founder|investor` → `400 {"error": "role must be one of: founder, investor"}`.
- **EF3** `OPENAI_API_KEY` unset / provider auth failure → the chat call fails (upstream 401),
  surfaced via the error handler. Unlike profile extraction, this endpoint cannot fall back.

## 8. Business Rules

- **BR1** Extraction is constrained by a strict role-specific JSON schema (founder vs investor
  attribute sets) with normalization rules (lowercased sectors, canonical stages
  `pre-seed|seed|series-a|series-b|growth`, lowercased regions, USD numeric amounts).
- **BR2** This endpoint requires the chat model; there is no keyless fallback for text
  extraction (the embedding step can still fall back, but attribute extraction cannot).
- **BR3** Upsert on unique `user_id`; source recorded as `"text"`.

## 9. Acceptance Criteria

- **AC1** With a valid key, a founder description returns `201` with `source: "text"`,
  `role: "founder"`, and founder-schema attributes.
- **AC2** An investor description returns `201` with investor-schema attributes.
- **AC3** Missing any required field returns EF1's exact 400 payload.
- **AC4** An invalid `role` returns EF2's exact 400 payload.
- **AC5** With `OPENAI_API_KEY` unset, the request fails at the chat-model call (EF3) rather
  than producing a row.

## 10. Cross-References

- Deterministic alternative (no key): [Extract from profile](extract-from-profile.md).
- Web-content variant: [Extract from crawl](extract-from-crawl.md).
- Read via: [Get extracted profile](get-extracted-profile.md); consumed by:
  [Find matches](../matching/find-matches.md).
