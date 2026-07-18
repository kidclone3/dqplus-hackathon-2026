#!/usr/bin/env bash
# Zero-downtime rolling deploy of the `web` service behind the `proxy`.
#
# Strategy: build the new image, start an extra `web` replica alongside the
# running one(s) and wait for it to become healthy, then gracefully drain the
# OLD replica(s). The proxy load-balances across replicas via Docker DNS and
# retries a sibling if one is draining, so the public port always has a healthy
# backend — no request is dropped.
#
# We drain the old containers by ID rather than `--scale` down, because
# `compose --scale N` removes the HIGHEST-numbered (newest) replicas, which
# would throw away the container we just deployed.
set -euo pipefail
cd "$(dirname "$0")/.."

SVC=web

echo "==> Building new '$SVC' image"
docker compose build "$SVC"

echo "==> Ensuring proxy is running"
docker compose up -d --no-deps proxy

OLD_IDS="$(docker compose ps -q "$SVC" || true)"

if [ -z "$OLD_IDS" ]; then
  echo "==> No running '$SVC' replica — starting fresh"
  docker compose up -d --no-deps --wait "$SVC"
  docker compose ps "$SVC"
  exit 0
fi

OLD_COUNT="$(printf '%s\n' "$OLD_IDS" | wc -l | tr -d ' ')"
NEW_SCALE=$((OLD_COUNT + 1))

echo "==> Starting new replica (scale $SVC=$NEW_SCALE, keeping old) and waiting for health"
docker compose up -d --no-deps --no-recreate --scale "$SVC=$NEW_SCALE" --wait "$SVC"

echo "==> New replica healthy. Draining old replica(s):"
printf '    %s\n' $OLD_IDS
# Graceful stop: in-flight requests finish; the proxy retries the new replica
# for anything that arrives during the swap.
docker stop $OLD_IDS >/dev/null
docker rm $OLD_IDS >/dev/null

echo "==> Reconciling desired state to scale=$SVC=1 (survivor kept, not recreated)"
docker compose up -d --no-deps --no-recreate --scale "$SVC=1" "$SVC"

echo "==> Done. Current '$SVC' replicas:"
docker compose ps "$SVC"
