# Extract Agent — E2E Tests

Runs against a **real** Postgres+pgvector (no DB or LLM mocking) and forces
`OPENAI_API_KEY=""` so the extraction pipeline exercises the deterministic
local feature-hash embedding fallback instead of calling an LLM.

```bash
uv sync
uv run pytest tests/e2e --json-report --json-report-file=tests/artifacts/test_results.json -v
```

Defaults (overridable via env): `DB_HOST=localhost`, `DB_PORT=5434`,
`DB_NAME=dealflow`, `DB_USER=dealflow`, `DB_PASSWORD=dealflow` — matching the
`dqplus-test-postgres` container. `tests/e2e/conftest.py` creates the
`users`/`profiles` tables (mirroring `backend/gateway`'s Sequelize models) if
they don't exist, plus runs `app/db/schema.sql`, and cleans up every row it
inserts.

## Coverage matrix

| Area | File | Cases |
|---|---|---|
| Health | `test_health.py` | `GET /health` → 200 `{status: ok, db: connected}` |
| `/extract/profile` | `test_extract_profile.py` | 201 founder mapping (`parse_number("500k")→500.0`, `to_list("Fintech, AI")→["fintech","ai"]`, `norm_stage("series_a")→"series-a"`, non-zero embedding stored); 201 investor mapping; re-POST upserts same row (`updated_at` bumps, row count stays 1); 400 missing `userId`; 404 no linked profile |
| `/extract/text` | `test_extract_text.py` | 400 missing fields; 400 bad `role` (LLM success path not covered — needs a real key) |
| `/extract/crawl` | `test_extract_crawl.py` | 400 missing fields; 400 bad `role` (LLM success path not covered — needs a real key) |
| `/extracted/{userId}` | `test_extracted_get.py` | 404 unknown user; 200 after a profile extraction |
| Embedding fallback | `test_embedding_fallback.py` | Bit-identical to the original Node `localEmbed` (verified against `node -e` output for two sample texts); deterministic; L2-normalized; empty-text zero vector |
