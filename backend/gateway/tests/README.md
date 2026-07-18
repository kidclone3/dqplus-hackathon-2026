# Gateway E2E tests

Real Postgres (no DB mocking): tests run against the `dqplus-test-postgres`
container (`localhost:5434`, db/user/pass `dealflow`, overridable via
`DB_HOST`/`DB_PORT`/`DB_NAME`/`DB_USER`/`DB_PASSWORD`). The app's own lifespan
bootstraps the schema (enum, `profiles`, `users`) on startup, same as
production.

`GET /matches` proxying is exercised against a real local FastAPI/uvicorn
server on an ephemeral port (a service-boundary double, not a mock of a DB or
LLM) — see `test_matches.py::upstream_matching_api`.

## Run

```bash
uv run pytest tests/e2e --json-report --json-report-file=tests/artifacts/test_results.json -v
```

## Coverage matrix

| AC / BR / EF | Behavior | Test |
|---|---|---|
| BR: register requires username+password+role | 400 when any is missing | `test_auth.py::test_register_missing_fields_400` |
| BR: role must be founder/investor | 400 for unknown role | `test_auth.py::test_register_invalid_role_400` |
| AC: `role=admin` rejected at register | 400, admin not creatable via API | `test_auth.py::test_register_admin_role_rejected` |
| BR: username uniqueness | 409 on duplicate | `test_auth.py::test_register_duplicate_username_409` |
| EF: register happy path | 201, `UserJSON` shape, token issued, no password field | `test_auth.py::test_register_happy_path` |
| BR: login requires username+password | 400 when missing | `test_auth.py::test_login_missing_fields_400` |
| BR: unknown user / bad password | 401 `Invalid credentials` | `test_auth.py::test_login_unknown_user_401`, `test_login_wrong_password_401` |
| EF: login happy path | 200, `UserJSON` + token | `test_auth.py::test_login_happy_path` |
| AC: admin provisioned only via direct DB write, can log in | insert admin row via asyncpg, login 200 | `test_auth.py::test_login_admin_provisioned_via_db` |
| EF: `/auth/me` happy path | 200, decoded JWT claims | `test_auth.py::test_me_happy_path` |
| BR: missing/malformed Authorization header | 401 `Missing or invalid Authorization header` | `test_auth.py::test_me_missing_header_401`, `test_me_malformed_header_401` |
| BR: invalid/expired token | 401 `Invalid or expired token` | `test_auth.py::test_me_invalid_token_401`, `test_me_expired_token_401` |
| BR: all `/profiles` routes require auth | 401 without a token on POST/GET/PATCH | `test_profiles.py::test_profiles_require_auth` |
| BR: `company_name` required | 400 on create | `test_profiles.py::test_create_profile_missing_company_name_400` |
| BR: JWT subject must reference an existing user | 404 `User not found` | `test_profiles.py::test_create_profile_user_not_found_404` |
| BR: one profile per user | 409 `User already has a profile` | `test_profiles.py::test_create_profile_already_has_profile_409` |
| EF: create profile happy path | 201, `ProfileJSON` shape, `users.profile_id` set | `test_profiles.py::test_create_profile_happy_path_and_links_user` |
| EF: get profile | 200 found / 404 missing | `test_profiles.py::test_get_profile_200`, `test_get_profile_404` |
| EF: patch profile | 200 updates only provided fields, bumps `updatedAt` | `test_profiles.py::test_patch_profile_200` |
| BR: patch requires ownership | 403 `Forbidden` when profile isn't the caller's | `test_profiles.py::test_patch_profile_forbidden_403` |
| BR: patch on a missing profile row | 404 `Profile not found` | `test_profiles.py::test_patch_profile_not_found_404` |
| EF: `GET /matches` proxy | passthrough status/body/query string, and the no-query-string case | `test_matches.py::test_matches_proxy_passthrough`, `test_matches_proxy_preserves_query_string_absence` |
| BR: upstream matching API failure | 500 `{"error": ...}` | `test_matches.py::test_matches_proxy_upstream_failure_500` |
| EF: health check | 200 `{"status":"ok","db":"connected"}` | `test_health.py::test_health_ok` |
| BR: unmatched route / wrong method | 404 `{"error":"Not found"}` | `test_health.py::test_not_found_unmatched_route`, `test_not_found_wrong_method` |
| Shape: error envelope | every error response is `{"error": <message>}` | asserted inline across all `4xx`/`5xx` tests above |
| Shape: timestamps | `YYYY-MM-DDTHH:MM:SS.sssZ` (JS `toISOString`) | `test_auth.py::test_register_happy_path`, `test_profiles.py::test_create_profile_happy_path_and_links_user` |
| Shape: numeric columns serialize as strings | `arr`/`avg_holding_period` come back as `"1000.00"` / `"2.50"` | `test_profiles.py::test_create_profile_happy_path_and_links_user`, `test_patch_profile_200` |
| Shape: `profileId` camelCase, null when unset | `test_auth.py::test_register_happy_path` |

## Deviation from spec

None. The one non-obvious wrinkle: `updateProfile`'s 404 "profile row
missing" branch can't be reached through any normal flow, because
`users.profile_id` has `ON DELETE SET NULL` — deleting a profile always nulls
the owning user's `profile_id` first, which trips the 403 branch instead.
There is also no `DELETE /profiles` endpoint. `test_patch_profile_not_found_404`
reaches the branch anyway by disabling the FK's delete trigger for the
duration of the delete, purely to exercise the defensive code path.
