# VietNexus — project rules for Claude

Innovation OS matching Vietnamese startups with investors/partners/universities.
Monorepo. Full stack runs in Docker (`docker-compose.yml`). Public site:
**https://dqplus.ddns.net**. Read [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md)
before making structural changes.

Matching (semantic **RAG** over a pgvector corpus + relationship **GraphRAG**) is served
by the **ai-data-platform** service (`:8000`); the old `matching-engine` is retired
(disabled via a compose `profiles: ["disabled"]` tag).

## Deployment — read before touching the live site

The public chain is: **VPS nginx → autossh SSH tunnel → local `:5173` → `proxy`
container → `web` replicas**. Only one container can bind a host port, so the
`web` service is internal-only and scaled behind the `proxy`.

- **Deploy a frontend change with `bash deploy/rolling-deploy.sh`.** It rolls a
  new `web` replica in and drains the old one with zero dropped requests. **Never**
  run `docker compose up -d --build web` against the live site — it stops the old
  container before the new one binds (seconds of downtime).
- **`web` must stay scalable**: no `container_name`, no published `ports:` — keep
  `expose: "80"`. The `proxy` service owns the public port (`WEB_PORT`, default 5173).
- **Edit `deploy/proxy.conf` → apply with `docker exec dqplus-proxy nginx -s reload`**
  (zero downtime). Recreating the `proxy` container briefly drops `:5173`.
- **The SSH tunnels** are managed by `deploy/port-forward.sh {start|stop|status}`
  (targets `127.0.0.1`, not the LAN IP — WSL2 mirrored networking makes
  docker-published ports unreachable via the LAN IP). Don't start tunnels by hand.
  `deploy/hackathonai.pem` and `deploy/port-forward.sh` are local-only (gitignored).
- **Public `/api/*` routing is per-service via dedicated reverse tunnels, NOT through
  the `web` nginx.** The VPS nginx maps each prefix to a tunnel port (`port-forward.sh`):
  `/api/backend`→5000→gateway, `/api/agents`→5002→extract,
  `/api/matches`→5003→**ai-data-platform:8000**, `/`→8443→`:5173`→web. So editing
  `frontend/nginx.conf` only changes the LOCAL `:5173` chain — the public `/api/matches`
  path is governed by the VPS nginx + the `5003` tunnel target.

## Gotchas learned the hard way

- **Container healthchecks must hit `127.0.0.1`, not `localhost`.** `localhost`
  resolves to `::1`; the services bind IPv4 only, so `localhost` reports a healthy
  container as unhealthy and hangs `docker compose --wait`.
- **`docker compose --scale web=N` scales *down* by removing the newest replica.**
  To roll, drain the *old* replica by container id (what `rolling-deploy.sh` does),
  never scale down.
- **Two Postgres, split by concern.** `dqplus-postgres` (host `:5433`, `DB_PORT`) holds
  ONLY user info — `users`/`profiles`/`extracted_profiles` — used by gateway + extract.
  `dqplus-platform-postgres` (host `:5432`, `PLATFORM_DB_PORT`) holds the ai-data-platform
  data — `entities`/`edges`/`matches`/sagas/jobs/…. The platform does **not** read user
  tables by SQL; it fetches profiles from **extract** over HTTP (`EXTRACT_SERVICE_URL`,
  `GET /extracted/:userId`). So `extract` is a hard dependency of matching — don't remove it.
  All host ports overridable via `.env`.
- **Gateway Dockerfile must not set `NODE_ENV=production`** — Sequelize `sync`
  (its only schema mechanism) is skipped in production.
- `OPENAI_API_KEY` is optional: empty → deterministic feature-hash embeddings, so the
  profile → match flow still works (no semantic embeddings). The ai-data-platform talks to
  the **FPT gateway** (`OPENAI_BASE_URL=https://mkp-api.fptcloud.com`) with embedder
  **`multilingual-e5-large` (1024-dim — not OpenAI models)** and needs a browser
  `User-Agent` on every call (FPT is behind Cloudflare, which 403s the default urllib UA).
  Its key/models live in `ai-data-platform/.env` (gitignored), scoped to that service via
  compose `env_file`. Corpus and query embeddings MUST use the same embedder.

## Conventions

- Secrets live in `.env` only (gitignored). Never commit keys, JWT secrets, or the pem.
- Frontend: Vite + React 18 + GSAP. Reuse the design tokens in `frontend/src/styles.css`
  (`--accent`, `--font-ui`/`--font-serif`, `.btn`/`.btn-primary`/`.btn-ghost`) — match
  the existing system, don't introduce a parallel one.
- CSS is global: namespace view-specific classes (e.g. landing uses `vn-lp-*`) to avoid
  collisions with other views' class names.
