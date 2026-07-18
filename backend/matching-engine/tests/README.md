# E2E test coverage

Run against a real Postgres + pgvector instance (no DB mocking):

```bash
uv run pytest tests/e2e --json-report --json-report-file=tests/artifacts/test_results.json -v
```

Defaults to `localhost:5434`, db/user/pass `dealflow` (matches the
`dqplus-test-postgres` container); override with `TEST_DB_HOST`,
`TEST_DB_PORT`, `TEST_DB_NAME`, `TEST_DB_USER`, `TEST_DB_PASSWORD`. The
`extracted_profiles` table (and the `vector` extension) is created if
missing, using the same DDL as `backend/agent/extract/src/db/schema.sql`.
Every test that seeds rows cleans them up afterward.

## Coverage matrix

| AC / behavior | Test |
|---|---|
| 404 when no extracted profile exists for the requester (founder→investor) | `test_matches_founders_investors.py::test_404_when_no_extracted_profile` |
| 404 when no extracted profile exists for the requester (investor→founder) | `test_matches_investors_founders.py::test_404_when_no_extracted_profile` |
| Ranking order follows composite score, descending | `test_matches_founders_investors.py::test_ranking_order_follows_composite_score`, `test_matches_investors_founders.py::test_ranking_order_follows_composite_score` |
| Vector score = pgvector cosine similarity (`1 - (a <=> b)`), exact value | `test_matches_founders_investors.py::test_exact_vector_and_attribute_score_math`, `test_matches_investors_founders.py::test_exact_vector_and_attribute_score_math` |
| Attribute score = jaccard(sector) + stage + region + funding-check-size blend, exact value | same as above (hand-computed: 0.4·(1/3) + 0.3 + 0.2 + 0.1 = 0.7333, composite 0.64; and 0.4·(1/3) + 0.3 + 0 + 0.1 = 0.5333, composite 0.58) |
| Composite score = round(VECTOR_WEIGHT·vector + ATTR_WEIGHT·attr, 4) | same as above |
| Reason strings: sector overlap, stage match, "investor invests globally", geography match, check size fits | `test_reasons_strings` in both direction files |
| No overlap → score 0.0, reasons `[]` | `test_reasons_strings` (worst-candidate assertions) in both direction files |
| Sector filter, case-insensitive | `test_sector_filter_is_case_insensitive` / `test_sector_filter` |
| Stage filter (array-contains for investor targets, exact-match for founder targets) | `test_stage_filter` / `test_stage_filter_exact_match` |
| Region filter is literal jsonb `?` containment — does NOT expand "global" (that's scoring-only) | `test_region_filter_is_literal_jsonb_containment` / `test_region_filter` |
| `limit=0` → falls back to default 10 (JS `Number(0) \|\| 10` is falsy, not clamped to 1) | `test_limit_zero_falls_back_to_default_ten` |
| Negative limit clamps to 1 | `test_negative_limit_clamps_to_one` |
| `limit=999` clamps to 50 | `test_limit_999_clamps_to_50` |
| Default limit is 10 | `test_default_limit_is_ten` |
| `GET /matches` proxies to `MATCHING_API_URL`, forwarding the raw query string, status, and content-type | `test_matches_proxy.py::test_matches_proxy_forwards_query_string_and_body` |
| `GET /health` reports `{"status":"ok","db":"connected"}` when DB is reachable | `test_health.py::test_health_ok` |
| Unmatched routes return `{"error":"Not found"}` with 404 | `test_not_found.py::test_unknown_route_returns_json_404` |

## Known deviation from the task brief

The brief's coverage list mentions "limit clamping (limit=0→1, ...)". The
actual Node source (`parseLimit` in `match.routes.js`, kept byte-for-byte as
the behavioral spec) is `Math.min(Math.max(Number(value) || 10, 1), 50)`.
Because `Number("0")` is `0`, which is falsy, `limit=0` is replaced by the
default of `10` before the `Math.max(n, 1)` clamp ever sees it — so `limit=0`
behaves identically to no `limit` at all, not to `limit=1`. The clamp-to-1
floor only fires for genuinely negative values (e.g. `limit=-5`). Both
behaviors are covered above; the implementation matches the Node source
exactly rather than the paraphrased test description.
