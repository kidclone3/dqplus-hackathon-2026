"""Postgres access via asyncpg (spec §5). SKIP LOCKED lease acquire, lease
expiry/reclaim, idempotent upserts, LISTEN/NOTIFY wake-ups."""
from __future__ import annotations

import json
from typing import Any, Awaitable, Callable

import asyncpg

from . import config, embedding, telemetry

JOBS_CHANNEL = "jobs_ready"

log = telemetry.get_logger("store")


def _to_pgvector(vec: list[float]) -> str:
    """pgvector text literal (bound as $1::vector), e.g. '[0.1,0.2,...]'."""
    return "[" + ",".join(str(float(x)) for x in vec) + "]"


class Store:
    def __init__(self, pool: asyncpg.Pool):
        self._pool = pool

    @classmethod
    async def connect(cls, dsn: str | None = None, *, min_size: int = 1,
                      max_size: int = 10) -> "Store":
        pool = await asyncpg.create_pool(
            dsn or config.DATABASE_URL, min_size=min_size, max_size=max_size
        )
        return cls(pool)

    async def close(self) -> None:
        await self._pool.close()

    # ---------- entities / edges ----------

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

    # ---------- artifacts / events ----------

    async def record_artifact(self, saga_id: str, step: str, payload: dict, *,
                              entity_id: str | None = None, target_id: str = "",
                              trace_id: str | None = None) -> None:
        """R6: latest-wins upsert on (saga_id, step, target_id)."""
        await self._pool.execute(
            """
            INSERT INTO artifacts (saga_id, step, entity_id, target_id, trace_id, payload)
            VALUES ($1, $2, $3, $4, $5, $6::jsonb)
            ON CONFLICT (saga_id, step, target_id) DO UPDATE
              SET payload = EXCLUDED.payload,
                  entity_id = EXCLUDED.entity_id,
                  trace_id = EXCLUDED.trace_id,
                  created_at = now()
            """,
            saga_id, step, entity_id, target_id, trace_id, json.dumps(payload),
        )

    async def get_artifact(self, saga_id: str, step: str, target_id: str = "") -> dict | None:
        row = await self._pool.fetchrow(
            "SELECT payload FROM artifacts WHERE saga_id = $1 AND step = $2 AND target_id = $3",
            saga_id, step, target_id,
        )
        return json.loads(row["payload"]) if row else None

    async def record_event(self, saga_id: str, seq: int, kind: str,
                           payload: dict | None = None, *, trace_id: str | None = None) -> None:
        await self._pool.execute(
            """
            INSERT INTO events (saga_id, seq, kind, trace_id, payload)
            VALUES ($1, $2, $3, $4, $5::jsonb)
            ON CONFLICT (saga_id, seq) DO NOTHING
            """,
            saga_id, seq, kind, trace_id,
            json.dumps(payload) if payload is not None else None,
        )

    # ---------- jobs (the queue) ----------

    async def enqueue_job(self, saga_id: str, stage: str, *, target_id: str = "",
                          agent: str | None = None, input_ref: dict | None = None,
                          trace_id: str | None = None) -> int | None:
        """Idempotent on (saga_id, stage, target_id) (R5). Returns job id, or None
        if the job already existed. Fires a LISTEN/NOTIFY wake-up."""
        row = await self._pool.fetchrow(
            """
            INSERT INTO jobs (saga_id, stage, target_id, agent, input_ref, trace_id)
            VALUES ($1, $2, $3, $4, $5::jsonb, $6)
            ON CONFLICT (saga_id, stage, target_id) DO NOTHING
            RETURNING id
            """,
            saga_id, stage, target_id, agent,
            json.dumps(input_ref) if input_ref is not None else None, trace_id,
        )
        if row is not None:
            await self._pool.execute("SELECT pg_notify($1, $2)", JOBS_CHANNEL, stage)
            return row["id"]
        return None

    async def acquire_job(self, worker_id: str, stages: list[str], *,
                          lease_seconds: int | None = None) -> asyncpg.Record | None:
        """Lease one ready job of a matching stage using FOR UPDATE SKIP LOCKED."""
        lease = lease_seconds or config.LEASE_SECONDS
        return await self._pool.fetchrow(
            """
            WITH nxt AS (
              SELECT id FROM jobs
              WHERE status = 'ready' AND stage = ANY($2::text[])
              ORDER BY id
              FOR UPDATE SKIP LOCKED
              LIMIT 1
            )
            UPDATE jobs
              SET status = 'leased',
                  leased_by = $1,
                  attempts = attempts + 1,
                  lease_expires_at = now() + make_interval(secs => $3),
                  leased_at = now()
            FROM nxt
            WHERE jobs.id = nxt.id
            RETURNING jobs.*
            """,
            worker_id, stages, lease,
        )

    async def reclaim_expired_leases(self) -> int:
        """A crashed worker's job auto-expires and is reclaimed (spec §5.3)."""
        rows = await self._pool.fetch(
            """
            UPDATE jobs
              SET status = 'ready', leased_by = NULL, lease_expires_at = NULL
            WHERE status = 'leased' AND lease_expires_at < now()
            RETURNING id
            """
        )
        return len(rows)

    async def complete_job(self, job_id: int) -> None:
        await self._pool.execute(
            "UPDATE jobs SET status = 'done', done_at = now() WHERE id = $1", job_id
        )

    async def fail_job(self, job_id: int, *, max_attempts: int = 3) -> str:
        """Mark failed; dead-letter once attempts exhausted. Returns new status."""
        row = await self._pool.fetchrow(
            """
            UPDATE jobs
              SET status = CASE WHEN attempts >= $2 THEN 'dead' ELSE 'ready' END,
                  leased_by = NULL, lease_expires_at = NULL
            WHERE id = $1
            RETURNING status
            """,
            job_id, max_attempts,
        )
        return row["status"] if row else "unknown"

    async def rearm_job(self, job_id: int, verify_feedback: dict) -> None:
        """R5: verify->draft retry — store feedback and re-arm the sub-job."""
        await self._pool.execute(
            """
            UPDATE jobs
              SET status = 'ready', leased_by = NULL, lease_expires_at = NULL,
                  verify_feedback = $2::jsonb
            WHERE id = $1
            """,
            job_id, json.dumps(verify_feedback),
        )

    # ---------- sagas ----------

    async def create_saga(self, saga_id: str, type_: str, subject_id: str | None, *,
                          current_step: str | None = None, trace_id: str | None = None) -> None:
        """Idempotent on saga_id (bootstrap re-run creates no duplicates)."""
        await self._pool.execute(
            """
            INSERT INTO saga_instances (saga_id, type, subject_id, current_step, trace_id)
            VALUES ($1, $2, $3, $4, $5)
            ON CONFLICT (saga_id) DO NOTHING
            """,
            saga_id, type_, subject_id, current_step, trace_id,
        )

    async def finish_stage(self, *, job_id: int, saga_id: str, event_kind: str,
                           saga_step: str, saga_status: str = "running",
                           event_payload: dict | None = None, trace_id: str | None = None,
                           next_stage: str | None = None, next_target_id: str = "",
                           next_agent: str | None = None,
                           next_input_ref: dict | None = None) -> None:
        """One transaction (spec §5.4): complete the job, append the milestone event,
        fold the saga projection, and enqueue the next stage — eliminating the dual-write
        problem. LISTEN/NOTIFY wake-up fires after commit."""
        enqueued = False
        async with self._pool.acquire() as conn:
            async with conn.transaction():
                await conn.execute(
                    "UPDATE jobs SET status = 'done', done_at = now() WHERE id = $1", job_id
                )
                seq = await conn.fetchval(
                    "SELECT COALESCE(MAX(seq), 0) + 1 FROM events WHERE saga_id = $1", saga_id
                )
                await conn.execute(
                    """
                    INSERT INTO events (saga_id, seq, kind, trace_id, payload)
                    VALUES ($1, $2, $3, $4, $5::jsonb)
                    ON CONFLICT (saga_id, seq) DO NOTHING
                    """,
                    saga_id, seq, event_kind, trace_id,
                    json.dumps(event_payload) if event_payload is not None else None,
                )
                await conn.execute(
                    """
                    UPDATE saga_instances
                      SET current_step = $2, status = $3, updated_at = now()
                    WHERE saga_id = $1
                    """,
                    saga_id, saga_step, saga_status,
                )
                if next_stage:
                    row = await conn.fetchrow(
                        """
                        INSERT INTO jobs (saga_id, stage, target_id, agent, input_ref, trace_id)
                        VALUES ($1, $2, $3, $4, $5::jsonb, $6)
                        ON CONFLICT (saga_id, stage, target_id) DO NOTHING
                        RETURNING id
                        """,
                        saga_id, next_stage, next_target_id, next_agent,
                        json.dumps(next_input_ref) if next_input_ref is not None else None,
                        trace_id,
                    )
                    enqueued = row is not None
        if next_stage and enqueued:
            await self._pool.execute("SELECT pg_notify($1, $2)", JOBS_CHANNEL, next_stage)

    async def get_saga(self, saga_id: str) -> dict | None:
        row = await self._pool.fetchrow(
            "SELECT saga_id, type, subject_id, current_step, status, trace_id "
            "FROM saga_instances WHERE saga_id = $1", saga_id
        )
        return dict(row) if row else None

    async def set_saga_status(self, saga_id: str, status: str,
                              *, current_step: str | None = None) -> None:
        await self._pool.execute(
            "UPDATE saga_instances SET status = $2, "
            "current_step = COALESCE($3, current_step), updated_at = now() "
            "WHERE saga_id = $1",
            saga_id, status, current_step,
        )

    async def count_active_jobs(self, saga_id: str, stages: list[str]) -> int:
        return await self._pool.fetchval(
            "SELECT count(*) FROM jobs WHERE saga_id = $1 AND stage = ANY($2::text[]) "
            "AND status IN ('ready', 'leased')",
            saga_id, stages,
        )

    async def get_job_row(self, saga_id: str, stage: str, target_id: str = "") -> dict | None:
        row = await self._pool.fetchrow(
            "SELECT * FROM jobs WHERE saga_id = $1 AND stage = $2 AND target_id = $3",
            saga_id, stage, target_id,
        )
        return dict(row) if row else None

    # ---------- matches (outreach domain results) ----------

    async def list_ready_partners(self) -> list[dict]:
        """All onboarded partner entities (candidates for the rule-filter)."""
        rows = await self._pool.fetch(
            "SELECT id, type, name, profile FROM entities "
            "WHERE type = ANY($1::text[]) AND status = 'ready'",
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
        """Idempotent on (startup_id, partner_id). Latest rank wins; preserves drafts on
        a re-rank by only overwriting rank columns."""
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

    # ---------- outreach DAG transitions ----------

    async def complete_and_fanout(self, *, job_id: int, saga_id: str, event_kind: str,
                                  event_payload: dict | None, saga_step: str,
                                  next_jobs: list[dict], saga_status: str = "running",
                                  trace_id: str | None = None) -> None:
        """One transaction (spec §5.4): complete the job, append the milestone event,
        fold the saga projection, and arm 0..N next jobs. Arming uses upsert-to-ready so
        a verify->draft retry (R5) can re-arm an already-completed verify job. A leased
        job is never disturbed. Wake-ups fire after commit."""
        async with self._pool.acquire() as conn:
            async with conn.transaction():
                await conn.execute(
                    "UPDATE jobs SET status = 'done', done_at = now() WHERE id = $1", job_id
                )
                seq = await conn.fetchval(
                    "SELECT COALESCE(MAX(seq), 0) + 1 FROM events WHERE saga_id = $1", saga_id
                )
                await conn.execute(
                    "INSERT INTO events (saga_id, seq, kind, trace_id, payload) "
                    "VALUES ($1,$2,$3,$4,$5::jsonb) ON CONFLICT (saga_id, seq) DO NOTHING",
                    saga_id, seq, event_kind, trace_id,
                    json.dumps(event_payload) if event_payload is not None else None,
                )
                await conn.execute(
                    "UPDATE saga_instances SET current_step = $2, status = $3, "
                    "updated_at = now() WHERE saga_id = $1",
                    saga_id, saga_step, saga_status,
                )
                for nj in next_jobs:
                    await conn.execute(
                        """
                        INSERT INTO jobs (saga_id, stage, target_id, agent, trace_id)
                        VALUES ($1,$2,$3,$4,$5)
                        ON CONFLICT (saga_id, stage, target_id) DO UPDATE
                          SET status = 'ready', leased_by = NULL, lease_expires_at = NULL,
                              agent = EXCLUDED.agent
                          WHERE jobs.status <> 'leased'
                        """,
                        saga_id, nj["stage"], nj["target_id"], nj.get("agent"), trace_id,
                    )
        for st in {nj["stage"] for nj in next_jobs}:
            await self._pool.execute("SELECT pg_notify($1, $2)", JOBS_CHANNEL, st)

    async def reject_and_rearm(self, *, verify_job_id: int, draft_job_id: int, saga_id: str,
                               feedback: dict, trace_id: str | None = None) -> None:
        """R5 verify->draft retry: close this verify attempt, record the rejection, and
        re-arm the draft sub-job carrying verify_feedback (attempts bump on re-lease)."""
        async with self._pool.acquire() as conn:
            async with conn.transaction():
                await conn.execute(
                    "UPDATE jobs SET status = 'done', done_at = now() WHERE id = $1",
                    verify_job_id,
                )
                seq = await conn.fetchval(
                    "SELECT COALESCE(MAX(seq), 0) + 1 FROM events WHERE saga_id = $1", saga_id
                )
                await conn.execute(
                    "INSERT INTO events (saga_id, seq, kind, trace_id, payload) "
                    "VALUES ($1,$2,'VerifyRejected',$3,$4::jsonb) "
                    "ON CONFLICT (saga_id, seq) DO NOTHING",
                    saga_id, seq, trace_id, json.dumps(feedback),
                )
                await conn.execute(
                    "UPDATE jobs SET status = 'ready', leased_by = NULL, "
                    "lease_expires_at = NULL, verify_feedback = $2::jsonb WHERE id = $1",
                    draft_job_id, json.dumps(feedback),
                )
        await self._pool.execute("SELECT pg_notify($1, $2)", JOBS_CHANNEL, "draft")

    async def dead_letter(self, *, job_ids: list[int], saga_id: str,
                          event_payload: dict | None, trace_id: str | None = None) -> None:
        """Retry budget exhausted (R5): mark the draft/verify sub-jobs dead; the match
        stays 'ranked' (not draft_ready)."""
        async with self._pool.acquire() as conn:
            async with conn.transaction():
                await conn.execute(
                    "UPDATE jobs SET status = 'dead', leased_by = NULL, "
                    "lease_expires_at = NULL WHERE id = ANY($1::bigint[])", job_ids
                )
                seq = await conn.fetchval(
                    "SELECT COALESCE(MAX(seq), 0) + 1 FROM events WHERE saga_id = $1", saga_id
                )
                await conn.execute(
                    "INSERT INTO events (saga_id, seq, kind, trace_id, payload) "
                    "VALUES ($1,$2,'DraftDeadLettered',$3,$4::jsonb) "
                    "ON CONFLICT (saga_id, seq) DO NOTHING",
                    saga_id, seq, trace_id,
                    json.dumps(event_payload) if event_payload is not None else None,
                )

    # ---------- workers (control plane) ----------

    async def register_worker(self, worker_id: str, *, agent_type: str, runtime: str,
                              boot_epoch: str, pid: int | None = None,
                              status: str = "busy", current_job_id: int | None = None) -> None:
        await self._pool.execute(
            """
            INSERT INTO workers (worker_id, agent_type, runtime, pid, boot_epoch,
                                 status, current_job_id, last_heartbeat_at)
            VALUES ($1, $2, $3, $4, $5, $6, $7, now())
            ON CONFLICT (worker_id) DO UPDATE
              SET status = EXCLUDED.status, pid = EXCLUDED.pid,
                  current_job_id = EXCLUDED.current_job_id, last_heartbeat_at = now()
            """,
            worker_id, agent_type, runtime, pid, boot_epoch, status, current_job_id,
        )

    async def set_worker_status(self, worker_id: str, status: str) -> None:
        await self._pool.execute(
            "UPDATE workers SET status = $2, last_heartbeat_at = now() WHERE worker_id = $1",
            worker_id, status,
        )

    # ---------- llm usage ----------

    async def record_usage(self, *, agent: str, runtime: str | None, model: str | None,
                           tokens_in: int | None, tokens_out: int | None,
                           cache_read: int | None, cache_write: int | None,
                           cost_usd: float | None, trace_id: str | None = None,
                           saga_id: str | None = None, job_id: int | None = None) -> None:
        await self._pool.execute(
            """
            INSERT INTO llm_usage (trace_id, saga_id, job_id, agent, runtime, model,
                                   tokens_in, tokens_out, cache_read, cache_write, cost_usd)
            VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11)
            """,
            trace_id, saga_id, job_id, agent, runtime, model,
            tokens_in, tokens_out, cache_read, cache_write, cost_usd,
        )

    # ---------- LISTEN/NOTIFY ----------

    async def listen(self, callback: Callable[[str], Awaitable[None] | None]) -> asyncpg.Connection:
        """Register a LISTEN on the jobs channel. Returns the dedicated connection
        (caller keeps it alive; close to stop listening)."""
        conn = await self._pool.acquire()

        def _handler(_conn, _pid, _channel, payload):
            res = callback(payload)
            if res is not None and hasattr(res, "__await__"):
                import asyncio
                asyncio.ensure_future(res)

        await conn.add_listener(JOBS_CHANNEL, _handler)
        return conn

    # ---------- raw access (supervisor / tests) ----------

    @property
    def pool(self) -> asyncpg.Pool:
        return self._pool
