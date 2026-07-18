#!/usr/bin/env bash
# Offline A1–A5 regression gate. Needs a reachable Postgres (docker compose up -d postgres).
set -euo pipefail
# Best-effort: bring Postgres up if it isn't already. Non-fatal because the port may
# already be served (e.g. by an existing compose stack); actual reachability is enforced
# below by NORTH_STAR_REQUIRE_DB, which hard-FAILS the gate if the DB can't be reached.
docker compose up -d postgres >/dev/null 2>&1 || true
# REQUIRE_DB=1 turns a down/misconfigured Postgres into a FAILURE, not a SKIP, so the
# gate can never go green without actually running the A1–A5 flow end-to-end.
# --strict-markers + -ra surfaces any skip; a gate run must show PASSED, never skipped.
NORTH_STAR_REQUIRE_DB=1 exec uv run pytest tests/test_north_star.py -v -ra \
  --strict-markers -m north_star
