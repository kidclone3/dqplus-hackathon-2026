"""Phase 4 hardening — crash recovery (spec §5.3, §9 RPC-integration row).

Proves: kill a worker mid-job -> its lease expires -> the job is reclaimed and
requeued -> a replacement finishes it -> the reclaimed/double-run job cannot create
a second artifact (UNIQUE(saga_id, step, target_id)) -> the saga completes.

Three angles:
  - store level:  lease -> crash (no write) -> reclaim -> re-lease -> write, then the
                  resurrected crashed worker double-writes -> still exactly ONE artifact.
  - supervisor:   end-to-end onboarding saga with the enrich worker dying mid-job on the
                  first attempt (ProcessDied) -> requeued -> second attempt succeeds ->
                  extract + link run -> saga 'done', entity 'ready', one artifact per step.
  - transport:    a real child process is SIGKILLed via its process group (close()),
                  proving the "kill a worker" mechanic actually reaps the OS process.
"""
import asyncio
import os
import sys
import uuid

import pytest

from spine.supervisor import Supervisor
from spine.transport import ProcessDied, RpcResult, TurnUsage


def _uid() -> str:
    return uuid.uuid4().hex[:8]


async def _lease_specific(store, job_id: int, lease_seconds: int = 120):
    """Lease one specific job by id (test isolation on a shared DB — the real
    acquire_job is not saga-scoped and would grab leftover ready jobs)."""
    return await store.pool.fetchrow(
        """
        UPDATE jobs SET status='leased', leased_by='test', attempts=attempts+1,
               lease_expires_at=now()+make_interval(secs=>$2), leased_at=now()
        WHERE id=$1 RETURNING *
        """,
        job_id, lease_seconds,
    )


async def _purge(store, saga_id: str, entity_id: str | None = None,
                 boot_epoch: str | None = None) -> None:
    async with store.pool.acquire() as conn:
        await conn.execute("DELETE FROM jobs WHERE saga_id=$1", saga_id)
        await conn.execute("DELETE FROM artifacts WHERE saga_id=$1", saga_id)
        await conn.execute("DELETE FROM events WHERE saga_id=$1", saga_id)
        await conn.execute("DELETE FROM saga_instances WHERE saga_id=$1", saga_id)
        if entity_id:
            await conn.execute("DELETE FROM edges WHERE src_id=$1", entity_id)
            await conn.execute("DELETE FROM entities WHERE id=$1", entity_id)
        if boot_epoch:
            await conn.execute("DELETE FROM workers WHERE boot_epoch=$1", boot_epoch)


# ---------------------------------------------------------------- store level

async def test_reclaim_after_crash_yields_no_double_artifact(store, saga_id):
    """Unique stage keeps acquire_job scoped to this test's single job."""
    stage = "enrich_" + _uid()
    eid = "startup:crashtest-" + _uid()
    jid = await store.enqueue_job(saga_id, stage, target_id=eid)
    assert jid is not None

    # worker A leases with an already-expired window, then "crashes" mid-job:
    # it never writes its artifact.
    job_a = await store.acquire_job("wA", [stage], lease_seconds=-1)
    assert job_a["id"] == jid and job_a["attempts"] == 1 and job_a["leased_by"] == "wA"

    # lease expired -> reclaimer requeues it.
    reclaimed = await store.reclaim_expired_leases()
    assert reclaimed >= 1
    row = await store.pool.fetchrow("SELECT status, leased_by FROM jobs WHERE id=$1", jid)
    assert row["status"] == "ready" and row["leased_by"] is None

    # replacement worker B leases the requeued job (attempts bumped -> 2) and does the work.
    job_b = await store.acquire_job("wB", [stage], lease_seconds=120)
    assert job_b["id"] == jid and job_b["attempts"] == 2 and job_b["leased_by"] == "wB"
    await store.record_artifact(saga_id, stage, {"result": "ok", "by": "wB"}, target_id=eid)
    await store.complete_job(jid)

    # the crashed worker A "resurrects" and re-writes the same (saga, step, target) —
    # the UNIQUE(saga_id, step, target_id) upsert makes this latest-wins, never a 2nd row.
    await store.record_artifact(saga_id, stage, {"result": "stale", "by": "wA"}, target_id=eid)

    n = await store.pool.fetchval(
        "SELECT count(*) FROM artifacts WHERE saga_id=$1 AND step=$2 AND target_id=$3",
        saga_id, stage, eid,
    )
    assert n == 1  # no double artifact
    await _purge(store, saga_id, entity_id=eid)


# ---------------------------------------------------------------- supervisor E2E

class _ScriptedChannel:
    """Duck-typed RpcChannel: either raises ProcessDied (crash) or returns a canned
    RpcResult. No real process, so _proc is None (pid -> None)."""

    def __init__(self, *, result: RpcResult | None = None, crash: bool = False):
        self._proc = None
        self._result = result
        self._crash = crash

    async def prompt(self, message: str, *, timeout: float = 300.0) -> RpcResult:
        if self._crash:
            raise ProcessDied("simulated worker crash mid-job")
        return self._result

    async def close(self) -> None:
        pass

    async def new_session(self) -> None:
        pass


class _ScriptedLauncher:
    def __init__(self, channels: list[_ScriptedChannel]):
        self._channels = list(channels)
        self.spawned: list[str] = []

    async def spawn(self, spec, worker_id, on_usage=None) -> _ScriptedChannel:
        self.spawned.append(worker_id)
        return self._channels.pop(0)


def _ok(data) -> RpcResult:
    return RpcResult(id=1, text="```json```", data=data,
                     usages=[TurnUsage(tokens_in=10, tokens_out=5, cost_usd=0.0001)])


async def test_supervisor_recovers_from_mid_job_crash_and_completes_saga(store):
    boot = "test-" + _uid()
    eid = "startup:e2ecrash-" + _uid()
    saga_id = "onboard:" + eid
    await store.upsert_entity(eid, "startup", "E2E Crash Co",
                              profile={"country": "Vietnam"}, status="seeded")
    await store.create_saga(saga_id, "onboarding", eid, current_step="enrich")
    enrich_jid = await store.enqueue_job(saga_id, "enrich", target_id=eid, agent="enricher")

    # spawn order: enrich(crash) -> enrich(ok) -> extract(ok). link is a code stage.
    launcher = _ScriptedLauncher([
        _ScriptedChannel(crash=True),
        _ScriptedChannel(result=_ok(
            {"entity_type": "startup",
             "profile": {"website": {"value": "https://e2ecrash.example.vn",
                                     "source_url": "https://e2ecrash.example.vn",
                                     "confidence": "high"}},
             "relationships": [], "collection_summary": {"status": "ok"}})),
        _ScriptedChannel(result=_ok(
            {"sectors": ["agritech"], "looking_for": ["funding"], "stage": "seed",
             "description_en": "x", "description_vi": "y"})),
    ])
    sup = Supervisor(store, boot_epoch=boot, launcher=launcher)

    # --- attempt 1: enrich worker dies mid-job ---
    job = await _lease_specific(store, enrich_jid)
    await sup._dispatch(job)
    row = await store.pool.fetchrow("SELECT status FROM jobs WHERE id=$1", enrich_jid)
    assert row["status"] == "ready"           # ProcessDied -> fail_job requeued it
    assert await store.get_artifact(saga_id, "enrich", eid) is None  # nothing persisted

    # --- attempt 2: replacement enrich worker succeeds ---
    job = await _lease_specific(store, enrich_jid)
    await sup._dispatch(job)
    row = await store.pool.fetchrow("SELECT status FROM jobs WHERE id=$1", enrich_jid)
    assert row["status"] == "done"
    assert await store.get_artifact(saga_id, "enrich", eid) is not None

    # --- extract (agent) ---
    extract_row = await store.get_job_row(saga_id, "extract", eid)
    assert extract_row is not None
    job = await _lease_specific(store, extract_row["id"])
    await sup._dispatch(job)

    # --- link (code) -> EntityReady, saga done ---
    link_row = await store.get_job_row(saga_id, "link", eid)
    assert link_row is not None
    job = await _lease_specific(store, link_row["id"])
    await sup._dispatch(job)

    # invariants: saga completed, entity ready, exactly one artifact per agent step.
    saga = await store.get_saga(saga_id)
    assert saga["status"] == "done"
    ent = await store.get_entity(eid)
    assert ent["status"] == "ready"
    for step in ("enrich", "extract"):
        cnt = await store.pool.fetchval(
            "SELECT count(*) FROM artifacts WHERE saga_id=$1 AND step=$2 AND target_id=$3",
            saga_id, step, eid,
        )
        assert cnt == 1, f"{step} should have exactly one artifact, got {cnt}"

    await _purge(store, saga_id, entity_id=eid, boot_epoch=boot)


# ---------------------------------------------------------------- transport kill

_FAKE_AGENT = r"""
import sys, json
# ACK, then hang forever holding stdin open — a worker stuck mid-job.
sys.stdout.write(json.dumps({"id": 1, "type": "response", "success": True}) + "\n")
sys.stdout.flush()
for line in sys.stdin:      # block until killed
    pass
"""


async def test_close_sigkills_the_process_group():
    """close() must reap the actual OS process (spec §4 close(): group-kill so a
    feynman shim's node child can't keep spending). Proves the kill mechanic."""
    from spine.transport import RpcChannel

    proc = await asyncio.create_subprocess_exec(
        sys.executable, "-c", _FAKE_AGENT,
        stdin=asyncio.subprocess.PIPE, stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE, start_new_session=True,
    )
    ch = RpcChannel(proc.stdin, proc.stdout, proc=proc)

    await asyncio.sleep(0.2)                   # let it ACK and settle into the read loop
    assert proc.returncode is None            # alive and holding mid-job
    await ch.close()                          # SIGKILL the whole group
    await asyncio.wait_for(proc.wait(), 5)
    assert proc.returncode is not None        # reaped
    # SIGKILL -> negative returncode (-9) on POSIX
    assert proc.returncode < 0
