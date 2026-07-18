# AI Data Platform — Roadmap

Component roadmap under the repo-level [system roadmap](../../docs/ROADMAP.md).
How the platform works today: [`ARCHITECTURE.md`](ARCHITECTURE.md) and
[`AGENT_FLOWS.md`](AGENT_FLOWS.md).

## Today

- **Deterministic spine**: event-sourced sagas, leased jobs, retries, dead-letter;
  `feynman` / `pi` agent runtimes over stdio JSON-RPC do the fuzzy work (enrich,
  extract, rank-explain, draft, verify). Every fact cited (`source_url`), unfound facts
  marked `unavailable`, drafts fact-checked by a second agent.
- **Serving the live `/matches` path** since the matching-engine cutover: pgvector RAG
  (FPT `multilingual-e5-large`, 1024-dim; blake2b feature-hash fallback) over the
  entity corpus + rule attribute scoring, self-fetching the requester from
  `extracted_profiles`, returning the legacy score/vectorScore/attributeScore/reasons
  shape.
- **GraphRAG** (`spine/graph.py`, BFS over `edges`) + `/entities/{id}/graph-matches`,
  semantic `/discover`, and the dashboard graph view.
- **Admin-gated dashboard** on `:8000` (`_verify_admin_jwt`); data endpoints public.
- Seed corpus of 115 entities embedded; migrations `001–004` applied via `bootstrap.py`.

## Phase 1 — Demo-hard

| Item | Definition of done |
|------|--------------------|
| Embedding activation is self-healing | On boot: verify migration 004 is applied and report corpus embedding coverage; a `NULL`-embedding corpus is a loud health-endpoint warning, not silently-empty matches |
| Embedder consistency contract | Model name + dimension stored alongside the corpus; queries with a mismatched embedder are rejected with a clear error (prevents the stale-container / wrong-key failure seen 2026-07-19) |
| Draft endpoint for the app | The bilingual, fact-checked draft saga exposed as a synchronous-feeling API the web client can call from match detail (job + poll or bounded wait) |
| Fail-open gate closed | Empty `JWT_SECRET` only fail-opens under an explicit standalone-dev flag |
| CI | `tests/` (incl. `test_dashboard_auth.py`) run on every push against the throwaway pgvector container |

## Phase 2 — Product

| Item | Definition of done |
|------|--------------------|
| Intent-specific match routes | Customer / partner / talent intents get dedicated routes with per-intent candidate filters and scoring rules (entity model already covers corporations, universities, research institutions) |
| Embed-on-upsert hardened | New/updated entities are embedded reliably (retry via the job machinery), retiring the best-effort `embed_on_upsert_failed` path and the manual `scripts/embed_entities.py` backfill |
| Corpus growth pipeline | Enrichment sagas run on a schedule against a curated source list; every new entity lands cited; dedup on ingest |
| Match outcome ingestion | Accept / pass / contacted events (from the backend) stored against matches for later ranking work |
| Cost & concurrency budget | Per-saga token/cost accounting on the pinned model, surfaced in the dashboard next to `MAX_CONCURRENCY` |

## Phase 3 — Scale & ecosystem

- **Learning-to-rank**: tune (then learn) vector/attribute weights per intent from the
  outcome signal; keep the explainable reasons — scores must stay auditable.
- **GraphRAG in the ranking loop**: relationship paths (co-investment, portfolio
  adjacency, university networks) contribute scored, cited rationale — not just the
  explorer view.
- **Fact freshness**: cited facts carry a checked-at timestamp; stale facts re-verified
  or demoted by a scheduled saga.
- **Multi-tenant corpora**: program/cohort scoping so accelerators run isolated views
  over shared public entities.
- **Runtime portability**: the agent-runtime port kept thin so `feynman`/`pi` can be
  swapped or upgraded without touching the spine contract.

## Standing constraints

- The spine stays deterministic: agents never get DB or network side-effect access;
  all I/O goes through the spine.
- No invented facts, ever — `unavailable` beats plausible. Verification rejects, it
  does not "fix".
- Every FPT call sends a browser User-Agent (Cloudflare 1010 gotcha); corpus and query
  must share one embedder.
- Schema changes only via `migrations/` (glob-applied by `bootstrap.py` on fresh boot;
  running DBs need explicit application).
