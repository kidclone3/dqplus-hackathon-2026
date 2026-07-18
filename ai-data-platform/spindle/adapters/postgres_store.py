"""PostgresStore — the PLATFORM-only store adapter (spec §B/§E, Seam 3).

Owns jobs/events/saga_instances/artifacts + the shared control-plane tables
(workers, llm_usage) and the LISTEN/NOTIFY edge. **Never touches app tables**
(entities/edges/matches live in `apps/matchmaker/store.py`).

Every job/event/saga/artifact method carries an ``app_id`` so one supervisor can
host arbitrary apps (spec §B). Job-id-keyed mutations (`complete_job`/`fail_job`)
and the SHARED control plane (`workers`, per spec §B) are deliberately *not*
app-scoped — a job id is globally unique and pools are shared across apps.

The SKIP LOCKED lease, the LISTEN/NOTIFY wake-up, and the single-transaction
event+job+saga write are preserved **verbatim** from the pre-cleave
`spine.store.Store` — they are the entire crash-recovery story (R5/R6). The only
change is threading ``app_id`` into the row writes; the retained narrow ON
CONFLICT arbiters (see migrations/004) still resolve idempotency while a single
app exists, and the app-scoped wide indexes are the forward bridge.
"""
from __future__ import annotations

import json
from typing import Awaitable, Callable

import asyncpg

from spine import config

JOBS_CHANNEL = "jobs_ready"


class PostgresStore:
    def __init__(self, pool: asyncpg.Pool):
        self._pool = pool

    @classmethod
    async def connect(cls, dsn: str | None = None, *, min_size: int = 1,
                      max_size: int = 10) -> "PostgresStore":
        pool = await asyncpg.create_pool(
            dsn or config.DATABASE_URL, min_size=min_size, max_size=max_size
        )
        return cls(pool)

    async def close(self) -> None:
        await self._pool.close()

    @property
    def pool(self) -> asyncpg.Pool:
        return self._pool

    # ---------- artifacts (generic blackboard) ----------

    async def record_artifact(self, app_id: str, saga_id: str, step: str, payload: dict, *,
                              entity_id: str | None = None, target_id: str = "",
                              trace_id: str | None = None) -> None:
        """R6: latest-wins upsert on (saga_id, step, target_id)."""
        await self._pool.execute(
            """
            INSERT INTO artifacts (app_id, saga_id, step, entity_id, target_id, trace_id, payload)
            VALUES ($1, $2, $3, $4, $5, $6, $7::jsonb)
            ON CONFLICT (saga_id, step, target_id) DO UPDATE
              SET payload = EXCLUDED.payload,
                  entity_id = EXCLUDED.entity_id,
                  trace_id = EXCLUDED.trace_id,
                  created_at = now()
            """,
            app_id, saga_id, step, entity_id, target_id, trace_id, json.dumps(payload),
        )

    async def get_artifact(self, app_id: str, saga_id: str, step: str,
                           target_id: str = "") -> dict | None:
        row = await self._pool.fetchrow(
            "SELECT payload FROM artifacts "
            "WHERE app_id = $1 AND saga_id = $2 AND step = $3 AND target_id = $4",
            app_id, saga_id, step, target_id,
        )
        return json.loads(row["payload"]) if row else None

    # ---------- events (append-only source of truth) ----------

    async def record_event(self, app_id: str, saga_id: str, seq: int, kind: str,
                           payload: dict | None = None, *, trace_id: str | None = None) -> None:
        await self._pool.execute(
            """
            INSERT INTO events (app_id, saga_id, seq, kind, trace_id, payload)
            VALUES ($1, $2, $3, $4, $5, $6::jsonb)
            ON CONFLICT (saga_id, seq) DO NOTHING
            """,
            app_id, saga_id, seq, kind, trace_id,
            json.dumps(payload) if payload is not None else None,
        )

    # ---------- jobs (the queue) ----------

    async def enqueue_job(self, app_id: str, saga_id: str, stage: str, *, target_id: str = "",
                          agent: str | None = None, input_ref: dict | None = None,
                          trace_id: str | None = None) -> int | None:
        """Idempotent on (saga_id, stage, target_id) (R5). Returns job id, or None
        if the job already existed. Fires a LISTEN/NOTIFY wake-up."""
        row = await self._pool.fetchrow(
            """
            INSERT INTO jobs (app_id, saga_id, stage, target_id, agent, input_ref, trace_id)
            VALUES ($1, $2, $3, $4, $5, $6::jsonb, $7)
            ON CONFLICT (saga_id, stage, target_id) DO NOTHING
            RETURNING id
            """,
            app_id, saga_id, stage, target_id, agent,
            json.dumps(input_ref) if input_ref is not None else None, trace_id,
        )
        if row is not None:
            await self._pool.execute("SELECT pg_notify($1, $2)", JOBS_CHANNEL, stage)
            return row["id"]
        return None

    async def acquire_job(self, worker_id: str, stages: list[str], *,
                          app_id: str | None = None,
                          lease_seconds: int | None = None) -> asyncpg.Record | None:
        """Lease one ready job of a matching stage using FOR UPDATE SKIP LOCKED.

        Pools are SHARED across apps (spec §B/§G3): with ``app_id=None`` a free
        worker leases any app's ready job; an ``app_id`` narrows to one app. The
        SKIP LOCKED contention-free lease is preserved verbatim."""
        lease = lease_seconds or config.LEASE_SECONDS
        return await self._pool.fetchrow(
            """
            WITH nxt AS (
              SELECT id FROM jobs
              WHERE status = 'ready' AND stage = ANY($2::text[])
                AND ($4::text IS NULL OR app_id = $4)
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
            worker_id, stages, lease, app_id,
        )

    async def reclaim_expired_leases(self, *, app_id: str | None = None) -> int:
        """A crashed worker's job auto-expires and is reclaimed (spec §5.3)."""
        rows = await self._pool.fetch(
            """
            UPDATE jobs
              SET status = 'ready', leased_by = NULL, lease_expires_at = NULL
            WHERE status = 'leased' AND lease_expires_at < now()
              AND ($1::text IS NULL OR app_id = $1)
            RETURNING id
            """,
            app_id,
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
        """R5 retry: store retry feedback and re-arm the sub-job back to 'ready'."""
        await self._pool.execute(
            """
            UPDATE jobs
              SET status = 'ready', leased_by = NULL, lease_expires_at = NULL,
                  verify_feedback = $2::jsonb
            WHERE id = $1
            """,
            job_id, json.dumps(verify_feedback),
        )

    # ---------- sagas (folded projection) ----------

    async def create_saga(self, app_id: str, saga_id: str, type_: str, subject_id: str | None, *,
                          current_step: str | None = None, trace_id: str | None = None) -> None:
        """Idempotent on saga_id (bootstrap re-run creates no duplicates)."""
        await self._pool.execute(
            """
            INSERT INTO saga_instances (app_id, saga_id, type, subject_id, current_step, trace_id)
            VALUES ($1, $2, $3, $4, $5, $6)
            ON CONFLICT (saga_id) DO NOTHING
            """,
            app_id, saga_id, type_, subject_id, current_step, trace_id,
        )

    async def finish_stage(self, app_id: str, *, job_id: int, saga_id: str, event_kind: str,
                           saga_step: str, saga_status: str = "running",
                           event_payload: dict | None = None, trace_id: str | None = None,
                           next_stage: str | None = None, next_target_id: str = "",
                           next_agent: str | None = None,
                           next_input_ref: dict | None = None) -> None:
        """One transaction (spec §5.4): complete the job, append the milestone event,
        fold the saga projection, and enqueue the next stage — eliminating the dual-write
        problem. Writes ONLY platform rows (queue+event+saga), never app tables.
        LISTEN/NOTIFY wake-up fires after commit."""
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
                    INSERT INTO events (app_id, saga_id, seq, kind, trace_id, payload)
                    VALUES ($1, $2, $3, $4, $5, $6::jsonb)
                    ON CONFLICT (saga_id, seq) DO NOTHING
                    """,
                    app_id, saga_id, seq, event_kind, trace_id,
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
                        INSERT INTO jobs (app_id, saga_id, stage, target_id, agent, input_ref, trace_id)
                        VALUES ($1, $2, $3, $4, $5, $6::jsonb, $7)
                        ON CONFLICT (saga_id, stage, target_id) DO NOTHING
                        RETURNING id
                        """,
                        app_id, saga_id, next_stage, next_target_id, next_agent,
                        json.dumps(next_input_ref) if next_input_ref is not None else None,
                        trace_id,
                    )
                    enqueued = row is not None
        if next_stage and enqueued:
            await self._pool.execute("SELECT pg_notify($1, $2)", JOBS_CHANNEL, next_stage)

    async def get_saga(self, app_id: str, saga_id: str) -> dict | None:
        row = await self._pool.fetchrow(
            "SELECT saga_id, type, subject_id, current_step, status, trace_id "
            "FROM saga_instances WHERE app_id = $1 AND saga_id = $2", app_id, saga_id
        )
        return dict(row) if row else None

    async def set_saga_status(self, app_id: str, saga_id: str, status: str,
                              *, current_step: str | None = None) -> None:
        await self._pool.execute(
            "UPDATE saga_instances SET status = $3, "
            "current_step = COALESCE($4, current_step), updated_at = now() "
            "WHERE app_id = $1 AND saga_id = $2",
            app_id, saga_id, status, current_step,
        )

    async def count_active_jobs(self, app_id: str, saga_id: str, stages: list[str]) -> int:
        return await self._pool.fetchval(
            "SELECT count(*) FROM jobs WHERE app_id = $1 AND saga_id = $2 "
            "AND stage = ANY($3::text[]) AND status IN ('ready', 'leased')",
            app_id, saga_id, stages,
        )

    async def get_job_row(self, app_id: str, saga_id: str, stage: str,
                          target_id: str = "") -> dict | None:
        row = await self._pool.fetchrow(
            "SELECT * FROM jobs "
            "WHERE app_id = $1 AND saga_id = $2 AND stage = $3 AND target_id = $4",
            app_id, saga_id, stage, target_id,
        )
        return dict(row) if row else None

    # ---------- DAG transitions (fan-out / reject / dead-letter) ----------

    async def complete_and_fanout(self, app_id: str, *, job_id: int, saga_id: str,
                                  event_kind: str, event_payload: dict | None, saga_step: str,
                                  next_jobs: list[dict], saga_status: str = "running",
                                  trace_id: str | None = None) -> None:
        """One transaction (spec §5.4): complete the job, append the milestone event,
        fold the saga projection, and arm 0..N next jobs. Arming uses upsert-to-ready so
        a reject->retry (R5) can re-arm an already-completed upstream job. A leased
        job is never disturbed. Writes ONLY platform rows. Wake-ups fire after commit."""
        async with self._pool.acquire() as conn:
            async with conn.transaction():
                await conn.execute(
                    "UPDATE jobs SET status = 'done', done_at = now() WHERE id = $1", job_id
                )
                seq = await conn.fetchval(
                    "SELECT COALESCE(MAX(seq), 0) + 1 FROM events WHERE saga_id = $1", saga_id
                )
                await conn.execute(
                    "INSERT INTO events (app_id, saga_id, seq, kind, trace_id, payload) "
                    "VALUES ($1,$2,$3,$4,$5,$6::jsonb) ON CONFLICT (saga_id, seq) DO NOTHING",
                    app_id, saga_id, seq, event_kind, trace_id,
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
                        INSERT INTO jobs (app_id, saga_id, stage, target_id, agent, trace_id)
                        VALUES ($1,$2,$3,$4,$5,$6)
                        ON CONFLICT (saga_id, stage, target_id) DO UPDATE
                          SET status = 'ready', leased_by = NULL, lease_expires_at = NULL,
                              agent = EXCLUDED.agent
                          WHERE jobs.status <> 'leased'
                        """,
                        app_id, saga_id, nj["stage"], nj["target_id"], nj.get("agent"), trace_id,
                    )
        for st in {nj["stage"] for nj in next_jobs}:
            await self._pool.execute("SELECT pg_notify($1, $2)", JOBS_CHANNEL, st)

    async def reject_and_rearm(self, app_id: str, *, reject_job_id: int, retry_job_id: int,
                               retry_stage: str, saga_id: str, feedback: dict,
                               event_kind: str = "StageRejected",
                               trace_id: str | None = None) -> None:
        """R5 reject->retry: close this rejected attempt, record the rejection event, and
        re-arm the retry sub-job carrying the feedback (attempts bump on re-lease)."""
        async with self._pool.acquire() as conn:
            async with conn.transaction():
                await conn.execute(
                    "UPDATE jobs SET status = 'done', done_at = now() WHERE id = $1",
                    reject_job_id,
                )
                seq = await conn.fetchval(
                    "SELECT COALESCE(MAX(seq), 0) + 1 FROM events WHERE saga_id = $1", saga_id
                )
                await conn.execute(
                    "INSERT INTO events (app_id, saga_id, seq, kind, trace_id, payload) "
                    "VALUES ($1,$2,$3,$4,$5,$6::jsonb) "
                    "ON CONFLICT (saga_id, seq) DO NOTHING",
                    app_id, saga_id, seq, event_kind, trace_id, json.dumps(feedback),
                )
                await conn.execute(
                    "UPDATE jobs SET status = 'ready', leased_by = NULL, "
                    "lease_expires_at = NULL, verify_feedback = $2::jsonb WHERE id = $1",
                    retry_job_id, json.dumps(feedback),
                )
        await self._pool.execute("SELECT pg_notify($1, $2)", JOBS_CHANNEL, retry_stage)

    async def dead_letter(self, app_id: str, *, job_ids: list[int], saga_id: str,
                          event_payload: dict | None, event_kind: str = "StageDeadLettered",
                          trace_id: str | None = None) -> None:
        """Retry budget exhausted (R5): mark the given sub-jobs dead and append the
        dead-letter milestone; the saga projection is left where it stands (no advance)."""
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
                    "INSERT INTO events (app_id, saga_id, seq, kind, trace_id, payload) "
                    "VALUES ($1,$2,$3,$4,$5,$6::jsonb) "
                    "ON CONFLICT (saga_id, seq) DO NOTHING",
                    app_id, saga_id, seq, event_kind, trace_id,
                    json.dumps(event_payload) if event_payload is not None else None,
                )

    # ---------- workers (SHARED control plane, not app-scoped per spec §B) ----------

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
