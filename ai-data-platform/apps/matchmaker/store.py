"""MatchmakerStore — the matchmaker app's data-access facade (spec §B/§E/§F, Seam 3).

The app owns its domain tables (entities/edges/matches) and composes the platform
adapter (:class:`spindle.adapters.postgres_store.PostgresStore`) for the generic
jobs/events/sagas/artifacts rows, hard-wiring ``app_id='matchmaker'`` — it is the
one app that knows its own identity. This is the app's store, not a platform shim:
the platform (`spindle/`) never imports it and holds no app knowledge; the app's
entrypoints (supervisor via the registry factory, scripts, API) and its plugin
handlers (via ``ctx.store``) drive it.

Split of concerns (Seam 3):
  - entity/edge/match SQL — the app's own tables, defined here directly.
  - artifacts / events / jobs / sagas / DAG transitions / workers / usage / NOTIFY —
    delegated to the app-scoped :class:`PostgresStore` (the single-transaction
    ``finish_stage``/``complete_and_fanout`` crash-recovery core, R5/R6, lives there).

Invariant (spec §E): a handler does its app-table write, then hands the platform a
declarative advance; the platform advance-in-txn writes the generic artifact row.
"""
from __future__ import annotations

import json
from typing import Awaitable, Callable

import asyncpg

from spindle.adapters.postgres_store import JOBS_CHANNEL, PostgresStore

from apps.matchmaker import embedding
from spine import config, telemetry

__all__ = ["MatchmakerStore", "JOBS_CHANNEL"]

APP_ID = "matchmaker"

log = telemetry.get_logger("store")


def _to_pgvector(vec: list[float]) -> str:
    """pgvector text literal (bound as $1::vector), e.g. '[0.1,0.2,...]'."""
    return "[" + ",".join(str(float(x)) for x in vec) + "]"


class MatchmakerStore:
    def __init__(self, pool: asyncpg.Pool):
        self._pool = pool
        self._platform = PostgresStore(pool)

    @classmethod
    async def connect(cls, dsn: str | None = None, *, min_size: int = 1,
                      max_size: int = 10) -> "MatchmakerStore":
        pool = await asyncpg.create_pool(
            dsn or config.DATABASE_URL, min_size=min_size, max_size=max_size
        )
        return cls(pool)

    async def close(self) -> None:
        await self._pool.close()

    @property
    def pool(self) -> asyncpg.Pool:
        return self._pool

    # ---------- entities / edges (app tables) ----------

    async def upsert_entity(self, entity_id: str, type_: str, name: str,
                            profile: dict | None = None, status: str = "seeded") -> None:
        await self._pool.execute(
            """
            INSERT INTO entities (id, type, name, profile, status)
            VALUES ($1, $2, $3, $4::jsonb, $5)
            ON CONFLICT (id) DO UPDATE
              SET type = EXCLUDED.type,
                  name = EXCLUDED.name,
                  profile = EXCLUDED.profile,
                  status = EXCLUDED.status,
                  updated_at = now()
            """,
            entity_id, type_, name, json.dumps(profile or {}), status,
        )
        # Keep entities.embedding current so new/enriched entities are searchable by the
        # EmbeddingMatcher immediately (in addition to scripts/embed_entities.py). Best-
        # effort: an embedding failure (endpoint down, etc.) must never fail onboarding.
        try:
            vec = await embedding.embed_text(
                embedding.entity_text({"name": name, "profile": profile or {}})
            )
            await self._pool.execute(
                "UPDATE entities SET embedding = $1::vector WHERE id = $2",
                _to_pgvector(vec), entity_id,
            )
        except Exception as e:  # noqa: BLE001 — onboarding must survive embedding errors
            log.warning("embed_on_upsert_failed", entity_id=entity_id, error=repr(e))

    async def get_entity(self, entity_id: str) -> dict | None:
        row = await self._pool.fetchrow(
            "SELECT id, type, name, profile, status FROM entities WHERE id = $1", entity_id
        )
        if row is None:
            return None
        d = dict(row)
        d["profile"] = json.loads(d["profile"]) if d["profile"] else {}
        return d

    async def upsert_edge(self, src_id: str, dst_id: str, kind: str, *,
                          dst_name: str | None = None, dst_resolved: bool = False,
                          source_url: str | None = None, payload: dict | None = None) -> None:
        """Idempotent on (src_id, dst_id, kind) — re-running enrichment cannot duplicate."""
        await self._pool.execute(
            """
            INSERT INTO edges (src_id, dst_id, kind, dst_name, dst_resolved, source_url, payload)
            VALUES ($1, $2, $3, $4, $5, $6, $7::jsonb)
            ON CONFLICT (src_id, dst_id, kind) DO UPDATE
              SET dst_name = EXCLUDED.dst_name,
                  dst_resolved = EXCLUDED.dst_resolved,
                  source_url = EXCLUDED.source_url,
                  payload = EXCLUDED.payload
            """,
            src_id, dst_id, kind, dst_name, dst_resolved, source_url,
            json.dumps(payload) if payload is not None else None,
        )

    async def delete_entities(self, entity_ids: list[str]) -> dict[str, int]:
        """Cleanup purge: remove graph data for the given ids in one transaction —
        matches/matches_v2 (FK + shadow), edges touching them, then the entities.
        Operational history (sagas/jobs/events/artifacts/llm_usage) is untouched."""
        counts: dict[str, int] = {}
        async with self._pool.acquire() as conn:
            async with conn.transaction():
                for table, cond in (
                    ("matches", "startup_id = ANY($1) OR partner_id = ANY($1)"),
                    ("matches_v2", "startup_id = ANY($1) OR partner_id = ANY($1)"),
                    ("edges", "src_id = ANY($1) OR dst_id = ANY($1)"),
                    ("entities", "id = ANY($1)"),
                ):
                    # matches_v2 is a lazily-created shadow table (scripts/
                    # dryrun_match_v2.py) — absent on fresh DBs; skip, don't abort.
                    if await conn.fetchval("SELECT to_regclass($1)", table) is None:
                        continue
                    tag = await conn.execute(
                        f"DELETE FROM {table} WHERE {cond}", entity_ids
                    )
                    counts[table] = int(tag.rsplit(" ", 1)[-1])
        return counts

    # ---------- matches (app tables) ----------

    async def list_ready_partners(self) -> list[dict]:
        """All onboarded partner entities (candidates for the rule-filter)."""
        rows = await self._pool.fetch(
            "SELECT id, type, name, profile FROM entities "
            "WHERE type = ANY($1::text[]) AND status = 'ready' ORDER BY id",
            ["investor", "corporation", "university", "research_institution"],
        )
        out = []
        for r in rows:
            d = dict(r)
            d["profile"] = json.loads(d["profile"]) if d["profile"] else {}
            out.append(d)
        return out

    async def upsert_match(self, *, startup_id: str, partner_id: str, composite: float | None,
                           semantic: float | None, sector_overlap: float | None,
                           rationale_en: str, rationale_vi: str, trace_id: str | None = None,
                           status: str = "ranked") -> None:
        """Idempotent on (startup_id, partner_id). Latest rank wins."""
        await self._pool.execute(
            """
            INSERT INTO matches (startup_id, partner_id, composite, semantic, sector_overlap,
                                 rationale_en, rationale_vi, trace_id, status)
            VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9)
            ON CONFLICT (startup_id, partner_id) DO UPDATE
              SET composite = EXCLUDED.composite,
                  semantic = EXCLUDED.semantic,
                  sector_overlap = EXCLUDED.sector_overlap,
                  rationale_en = EXCLUDED.rationale_en,
                  rationale_vi = EXCLUDED.rationale_vi,
                  trace_id = EXCLUDED.trace_id,
                  status = EXCLUDED.status
            """,
            startup_id, partner_id, composite, semantic, sector_overlap,
            rationale_en, rationale_vi, trace_id, status,
        )

    async def get_match(self, startup_id: str, partner_id: str) -> dict | None:
        row = await self._pool.fetchrow(
            "SELECT * FROM matches WHERE startup_id = $1 AND partner_id = $2",
            startup_id, partner_id,
        )
        return dict(row) if row else None

    async def set_match_draft(self, startup_id: str, partner_id: str,
                              draft_en: str, draft_vi: str) -> None:
        await self._pool.execute(
            "UPDATE matches SET draft_en = $3, draft_vi = $4 "
            "WHERE startup_id = $1 AND partner_id = $2",
            startup_id, partner_id, draft_en, draft_vi,
        )

    async def set_match_status(self, startup_id: str, partner_id: str, status: str) -> None:
        await self._pool.execute(
            "UPDATE matches SET status = $3 WHERE startup_id = $1 AND partner_id = $2",
            startup_id, partner_id, status,
        )

    # ---------- artifacts / events (platform, app_id-scoped blackboard) ----------

    async def record_artifact(self, saga_id: str, step: str, payload: dict, *,
                              entity_id: str | None = None, target_id: str = "",
                              trace_id: str | None = None) -> None:
        await self._platform.record_artifact(APP_ID, saga_id, step, payload,
                                             entity_id=entity_id, target_id=target_id,
                                             trace_id=trace_id)

    async def get_artifact(self, saga_id: str, step: str, target_id: str = "") -> dict | None:
        return await self._platform.get_artifact(APP_ID, saga_id, step, target_id)

    async def record_event(self, saga_id: str, seq: int, kind: str,
                           payload: dict | None = None, *, trace_id: str | None = None) -> None:
        await self._platform.record_event(APP_ID, saga_id, seq, kind, payload,
                                          trace_id=trace_id)

    # ---------- jobs (platform) ----------

    async def enqueue_job(self, saga_id: str, stage: str, *, target_id: str = "",
                          agent: str | None = None, input_ref: dict | None = None,
                          trace_id: str | None = None) -> int | None:
        return await self._platform.enqueue_job(APP_ID, saga_id, stage, target_id=target_id,
                                                agent=agent, input_ref=input_ref,
                                                trace_id=trace_id)

    async def acquire_job(self, worker_id: str, stages: list[str], *,
                          lease_seconds: int | None = None) -> asyncpg.Record | None:
        return await self._platform.acquire_job(worker_id, stages, app_id=APP_ID,
                                                lease_seconds=lease_seconds)

    async def reclaim_expired_leases(self) -> int:
        return await self._platform.reclaim_expired_leases(app_id=APP_ID)

    async def complete_job(self, job_id: int) -> None:
        await self._platform.complete_job(job_id)

    async def fail_job(self, job_id: int, *, max_attempts: int = 3) -> str:
        return await self._platform.fail_job(job_id, max_attempts=max_attempts)

    async def rearm_job(self, job_id: int, verify_feedback: dict) -> None:
        await self._platform.rearm_job(job_id, verify_feedback)

    # ---------- sagas (platform) ----------

    async def create_saga(self, saga_id: str, type_: str, subject_id: str | None, *,
                          current_step: str | None = None, trace_id: str | None = None) -> None:
        await self._platform.create_saga(APP_ID, saga_id, type_, subject_id,
                                         current_step=current_step, trace_id=trace_id)

    async def finish_stage(self, *, job_id: int, saga_id: str, event_kind: str,
                           saga_step: str, saga_status: str = "running",
                           event_payload: dict | None = None, trace_id: str | None = None,
                           next_stage: str | None = None, next_target_id: str = "",
                           next_agent: str | None = None,
                           next_input_ref: dict | None = None) -> None:
        await self._platform.finish_stage(
            APP_ID, job_id=job_id, saga_id=saga_id, event_kind=event_kind,
            saga_step=saga_step, saga_status=saga_status, event_payload=event_payload,
            trace_id=trace_id, next_stage=next_stage, next_target_id=next_target_id,
            next_agent=next_agent, next_input_ref=next_input_ref,
        )

    async def get_saga(self, saga_id: str) -> dict | None:
        return await self._platform.get_saga(APP_ID, saga_id)

    async def set_saga_status(self, saga_id: str, status: str,
                              *, current_step: str | None = None) -> None:
        await self._platform.set_saga_status(APP_ID, saga_id, status, current_step=current_step)

    async def count_active_jobs(self, saga_id: str, stages: list[str]) -> int:
        return await self._platform.count_active_jobs(APP_ID, saga_id, stages)

    async def get_job_row(self, saga_id: str, stage: str, target_id: str = "") -> dict | None:
        return await self._platform.get_job_row(APP_ID, saga_id, stage, target_id)

    # ---------- DAG transitions (platform) ----------

    async def complete_and_fanout(self, *, job_id: int, saga_id: str, event_kind: str,
                                  event_payload: dict | None, saga_step: str,
                                  next_jobs: list[dict], saga_status: str = "running",
                                  trace_id: str | None = None) -> None:
        await self._platform.complete_and_fanout(
            APP_ID, job_id=job_id, saga_id=saga_id, event_kind=event_kind,
            event_payload=event_payload, saga_step=saga_step, next_jobs=next_jobs,
            saga_status=saga_status, trace_id=trace_id,
        )

    async def reject_and_rearm(self, *, verify_job_id: int, draft_job_id: int, saga_id: str,
                               feedback: dict, trace_id: str | None = None) -> None:
        await self._platform.reject_and_rearm(
            APP_ID, reject_job_id=verify_job_id, retry_job_id=draft_job_id,
            retry_stage="draft", saga_id=saga_id, feedback=feedback,
            event_kind="VerifyRejected", trace_id=trace_id,
        )

    async def dead_letter(self, *, job_ids: list[int], saga_id: str,
                          event_payload: dict | None, trace_id: str | None = None) -> None:
        await self._platform.dead_letter(
            APP_ID, job_ids=job_ids, saga_id=saga_id, event_payload=event_payload,
            event_kind="DraftDeadLettered", trace_id=trace_id,
        )

    # ---------- workers / usage (platform, shared control plane) ----------

    async def register_worker(self, worker_id: str, *, agent_type: str, runtime: str,
                              boot_epoch: str, pid: int | None = None,
                              status: str = "busy", current_job_id: int | None = None) -> None:
        await self._platform.register_worker(
            worker_id, agent_type=agent_type, runtime=runtime, boot_epoch=boot_epoch,
            pid=pid, status=status, current_job_id=current_job_id,
        )

    async def set_worker_status(self, worker_id: str, status: str) -> None:
        await self._platform.set_worker_status(worker_id, status)

    async def record_usage(self, *, agent: str, runtime: str | None, model: str | None,
                           tokens_in: int | None, tokens_out: int | None,
                           cache_read: int | None, cache_write: int | None,
                           cost_usd: float | None, trace_id: str | None = None,
                           saga_id: str | None = None, job_id: int | None = None) -> None:
        await self._platform.record_usage(
            agent=agent, runtime=runtime, model=model, tokens_in=tokens_in,
            tokens_out=tokens_out, cache_read=cache_read, cache_write=cache_write,
            cost_usd=cost_usd, trace_id=trace_id, saga_id=saga_id, job_id=job_id,
        )

    # ---------- LISTEN/NOTIFY (platform) ----------

    async def listen(self, callback: Callable[[str], Awaitable[None] | None]) -> asyncpg.Connection:
        return await self._platform.listen(callback)
