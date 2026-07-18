"""Supervisor skeleton — the reconciler (spec §5.2, §5.3).

Postgres is the source of truth for desired + leased state; the supervisor is a
reconciler, not the record. This Phase-0 skeleton wires the loop shape:
  - reconcile_on_boot: adopt survivors, kill prior-epoch orphans, reclaim leases
  - a periodic lease-reclaim + heartbeat tick
  - a scheduler loop that leases ready jobs and dispatches them (dispatch is
    filled in Phase 1/2 with real agent pools)

Entrypoint: `python -m spine.supervisor` (R4).
"""
from __future__ import annotations

import asyncio
import os
import signal
import uuid

from . import cleanup, config, outreach, pools, sagas, telemetry
from .matcher.llm_judge import LlmJudgeMatcher
from .store import Store
from .transport import LocalProcessLauncher, ProcessDied, RpcResult

log = telemetry.get_logger("supervisor")


class Supervisor:
    def __init__(self, store: Store, *, boot_epoch: str | None = None,
                 reclaim_interval: float = 3.0, launcher: LocalProcessLauncher | None = None,
                 specs_path: str = pools.DEFAULT_PATH, stages: list[str] | None = None):
        self.store = store
        self.boot_epoch = boot_epoch or uuid.uuid4().hex
        self.reclaim_interval = reclaim_interval
        if launcher is None:
            # Contain agent `write`-tool scratch in a gitignored dir (feynman discovers
            # its skills globally, so cwd only affects tool working directory).
            scratch = os.path.join(os.getcwd(), ".agent-scratch")
            os.makedirs(scratch, exist_ok=True)
            launcher = LocalProcessLauncher(cwd=scratch)
        self.launcher = launcher
        self.specs = pools.load_specs(specs_path)
        self.by_stage = pools.specs_by_stage(self.specs)
        # All sagas drain in one supervisor run: onboarding + outreach + cleanup.
        # `stages` restricts the run (e.g. scripts/cleanup.py drains only cleanup
        # without leasing stale jobs from the other sagas).
        self._all_stages = stages or (sagas.ONBOARDING_STAGES + outreach.OUTREACH_STAGES
                                      + cleanup.CLEANUP_STAGES)
        self._agent_stages = (sagas.AGENT_STAGES | outreach.OUTREACH_AGENT_STAGES
                              | cleanup.CLEANUP_AGENT_STAGES)
        self._sem = asyncio.Semaphore(config.MAX_CONCURRENCY)
        self._stop = asyncio.Event()

    async def reconcile_on_boot(self) -> None:
        """Read non-dead workers; prior-epoch rows are orphans → mark dead and
        reclaim their leases. (Killing OS orphans lands with real pools.)"""
        async with self.store.pool.acquire() as conn:
            orphans = await conn.fetch(
                "SELECT worker_id, pid FROM workers "
                "WHERE status <> 'dead' AND boot_epoch <> $1",
                self.boot_epoch,
            )
            if orphans:
                await conn.execute(
                    "UPDATE workers SET status = 'dead' "
                    "WHERE status <> 'dead' AND boot_epoch <> $1",
                    self.boot_epoch,
                )
        reclaimed = await self.store.reclaim_expired_leases()
        log.info("reconcile_on_boot", boot_epoch=self.boot_epoch,
                 orphans=len(orphans), leases_reclaimed=reclaimed)

    async def _reclaim_loop(self) -> None:
        while not self._stop.is_set():
            n = await self.store.reclaim_expired_leases()
            if n:
                log.info("leases_reclaimed", count=n)
            try:
                await asyncio.wait_for(self._stop.wait(), self.reclaim_interval)
            except asyncio.TimeoutError:
                pass

    async def _schedule_loop(self) -> None:
        """Competing-consumer scheduler: lease ready onboarding jobs and dispatch each
        as a bounded background task (global cap = MAX_CONCURRENCY). Woken by
        LISTEN/NOTIFY; falls back to a poll so nothing stalls if a notify is missed."""
        wake = asyncio.Event()
        conn = await self.store.listen(lambda _payload: wake.set())
        active: set[asyncio.Task] = set()
        try:
            while not self._stop.is_set():
                if len(active) >= config.MAX_CONCURRENCY:
                    await asyncio.sleep(0.1)
                    continue
                job = await self.store.acquire_job(
                    worker_id=f"sup:{self.boot_epoch}", stages=self._all_stages,
                )
                if job is None:
                    wake.clear()
                    try:
                        await asyncio.wait_for(wake.wait(), 0.5)
                    except asyncio.TimeoutError:
                        pass
                    continue
                t = asyncio.create_task(self._dispatch(job))
                active.add(t)
                t.add_done_callback(active.discard)
        finally:
            if active:
                await asyncio.gather(*active, return_exceptions=True)
            await self.store.pool.release(conn)

    async def _dispatch(self, job) -> None:
        job_id, stage = job["id"], job["stage"]
        telemetry.bind(job_id=job_id, saga_id=job["saga_id"],
                       trace_id=job["trace_id"], stage=stage)
        try:
            if stage in sagas.AGENT_STAGES:              # enrich | extract (feynman)
                await self._onboard_agent_stage(job)
            elif stage == "link":                        # code
                log.info("link_stage", target_id=job["target_id"])
                await sagas.link(self.store, job)
                log.info("entity_ready", target_id=job["target_id"])
            elif stage == "filter":                      # code (outreach)
                log.info("filter_stage", target_id=job["target_id"])
                await outreach.filter_stage(self.store, job)
            elif stage == "match":                       # pi via Matcher port (R12)
                await self._match_stage(job)
            elif stage == "draft":                       # pi, per match
                await self._draft_stage(job)
            elif stage == "verify":                      # pi, per match
                await self._verify_stage(job)
            elif stage == "audit":                       # pi (cleanup janitor)
                await self._audit_stage(job)
            elif stage == "purge":                       # code (cleanup)
                log.info("purge_stage", prefix=job["target_id"])
                await cleanup.purge(self.store, job)
                log.info("cleanup_done", prefix=job["target_id"])
            else:
                log.warning("unknown_stage", stage=stage)
                await self.store.fail_job(job_id)
        except ProcessDied as e:
            log.warning("agent_process_died", error=str(e))
            await self.store.fail_job(job_id)
        except Exception as e:
            log.error("dispatch_error", error=repr(e))
            await self.store.fail_job(job_id)
        finally:
            telemetry.clear()

    async def _run_worker(self, spec, prompt: str, job) -> RpcResult:
        """Spawn a fresh RPC process, run one prompt, record usage, kill it. A fresh
        process per job is the R7 session-hygiene fallback (N=1) — no warm-context bleed
        between targets. Works for both runtimes (the launcher picks the CLI)."""
        job_id = job["id"]
        worker_id = f"{spec.name}:{self.boot_epoch}:{job_id}"
        async with self._sem:
            ch = await self.launcher.spawn(spec, worker_id)
            pid = ch._proc.pid if ch._proc else None
            await self.store.register_worker(
                worker_id, agent_type=spec.name, runtime=spec.runtime,
                boot_epoch=self.boot_epoch, pid=pid, status="busy",
                current_job_id=job_id,
            )
            log.info("agent_prompt", worker_id=worker_id, target_id=job["target_id"])
            try:
                result = await ch.prompt(prompt, timeout=config.AGENT_TIMEOUT)
            finally:
                await ch.close()
                await self.store.set_worker_status(worker_id, "dead")

        for u in result.usages:
            await self.store.record_usage(
                agent=spec.name, runtime=spec.runtime, model=spec.model,
                tokens_in=u.tokens_in, tokens_out=u.tokens_out,
                cache_read=u.cache_read, cache_write=u.cache_write,
                cost_usd=u.cost_usd, trace_id=job["trace_id"],
                saga_id=job["saga_id"], job_id=job_id,
            )
        cost = sum((u.cost_usd or 0) for u in result.usages)
        log.info("agent_turns", turns=len(result.usages), cost_usd=round(cost, 6),
                 success=result.success)
        return result

    async def _onboard_agent_stage(self, job) -> None:
        """enrich/extract (feynman): prompt → validate JSON (R3) → persist + advance."""
        stage = job["stage"]
        spec = self.by_stage[stage]
        prompt = await sagas.build_prompt(stage, job, self.store)
        result = await self._run_worker(spec, prompt, job)
        if not result.success or not sagas.validate(stage, result.data):
            log.warning("agent_reject", stop_reason=result.stop_reason,
                        error=result.error_message, has_data=result.data is not None)
            status = await self.store.fail_job(job["id"])  # re-arm; prompt strengthens
            log.info("job_failed", new_status=status)
            return
        await sagas.persist_and_advance(self.store, job, result.data)

    async def _audit_stage(self, job) -> None:
        """cleanup audit (pi janitor): prompt → validate verdicts (R3) → advance to purge."""
        spec = self.by_stage["audit"]
        prompt = await cleanup.build_prompt(job, self.store)
        result = await self._run_worker(spec, prompt, job)
        if not result.success or not cleanup.validate(result.data):
            log.warning("audit_reject", stop_reason=result.stop_reason,
                        error=result.error_message, has_data=result.data is not None)
            status = await self.store.fail_job(job["id"])
            log.info("job_failed", new_status=status)
            return
        await cleanup.persist_and_advance(self.store, job, result.data)

    async def _startup_id(self, job) -> str:
        saga = await self.store.get_saga(job["saga_id"])
        return saga["subject_id"] if saga else job["saga_id"].split("outreach:", 1)[-1]

    async def _match_stage(self, job) -> None:
        """Agent-backed rank+explain (R12). The Matcher port abstracts ranking; v1
        LlmJudgeMatcher runs one pi call over the filtered handful, then we persist
        matches (status='ranked') and fan out per-match draft jobs (R5)."""
        saga_id, startup_id, job_id = job["saga_id"], job["target_id"], job["id"]
        startup = await self.store.get_entity(startup_id)
        art = await self.store.get_artifact(saga_id, "filter", startup_id) or {}
        cand_ids = [c["partner_id"] for c in art.get("candidates", [])]
        candidates = [await self.store.get_entity(pid) for pid in cand_ids]
        candidates = [c for c in candidates if c is not None]

        spec = self.by_stage["match"]

        async def runner(prompt: str) -> RpcResult:
            return await self._run_worker(spec, prompt, job)

        matcher = LlmJudgeMatcher(runner, top_k=config.MATCH_TOP_K)
        scored = await matcher.rank(startup, candidates,
                                    ctx={"retry": (job["attempts"] or 0) > 1})
        if not scored:
            log.warning("match_empty")
            status = await self.store.fail_job(job_id, max_attempts=config.MAX_ATTEMPTS)
            log.info("job_failed", new_status=status)
            return

        top = scored[: config.MATCH_TOP_K]
        for m in top:
            await self.store.upsert_match(
                startup_id=startup_id, partner_id=m.partner_id,
                composite=m.composite, semantic=m.semantic,
                sector_overlap=m.sector_overlap, rationale_en=m.rationale_en,
                rationale_vi=m.rationale_vi, trace_id=job["trace_id"], status="ranked",
            )
        next_jobs = [{"stage": "draft", "target_id": m.partner_id, "agent": "drafter"}
                     for m in top]
        log.info("matches_ranked", count=len(top),
                 partners=[m.partner_id for m in top])
        await self.store.complete_and_fanout(
            job_id=job_id, saga_id=saga_id, event_kind="MatchesRanked",
            event_payload={"startup_id": startup_id,
                           "partners": [m.partner_id for m in top]},
            saga_step="draft", next_jobs=next_jobs, trace_id=job["trace_id"],
        )

    async def _draft_stage(self, job) -> None:
        """Per-match draft (pi, dealflow-match §4). Carries verify_feedback on retry (R5)."""
        saga_id, partner_id, job_id = job["saga_id"], job["target_id"], job["id"]
        startup_id = await self._startup_id(job)
        startup = await self.store.get_entity(startup_id)
        partner = await self.store.get_entity(partner_id)
        match = await self.store.get_match(startup_id, partner_id) or {}
        feedback = job.get("verify_feedback")
        if isinstance(feedback, str):
            import json as _json
            feedback = _json.loads(feedback)

        prompt = outreach.draft_prompt(startup, partner, match, verify_feedback=feedback,
                                       retry=(job["attempts"] or 0) > 1)
        result = await self._run_worker(self.by_stage["draft"], prompt, job)
        if not result.success or not outreach.validate("draft", result.data):
            status = await self.store.fail_job(job_id, max_attempts=config.MAX_ATTEMPTS)
            log.warning("draft_reject", new_status=status, error=result.error_message)
            return

        data = result.data
        await self.store.set_match_draft(startup_id, partner_id,
                                         data["draft_en"], data["draft_vi"])
        log.info("draft_ready", partner_id=partner_id)
        await self.store.complete_and_fanout(
            job_id=job_id, saga_id=saga_id, event_kind="DraftReady",
            event_payload={"partner_id": partner_id}, saga_step="verify",
            next_jobs=[{"stage": "verify", "target_id": partner_id, "agent": "verifier"}],
            trace_id=job["trace_id"],
        )

    async def _verify_stage(self, job) -> None:
        """Per-match verify (pi, draft-verify LLM-judge). pass → draft_ready; fail →
        re-arm the draft sub-job with feedback (R5), or dead-letter once attempts exhaust."""
        saga_id, partner_id, job_id = job["saga_id"], job["target_id"], job["id"]
        startup_id = await self._startup_id(job)
        startup = await self.store.get_entity(startup_id)
        partner = await self.store.get_entity(partner_id)
        match = await self.store.get_match(startup_id, partner_id) or {}

        prompt = outreach.verify_prompt(startup, partner, match,
                                        retry=(job["attempts"] or 0) > 1)
        result = await self._run_worker(self.by_stage["verify"], prompt, job)
        if not result.success or not outreach.validate("verify", result.data):
            status = await self.store.fail_job(job_id, max_attempts=config.MAX_ATTEMPTS)
            log.warning("verify_reject", new_status=status, error=result.error_message)
            return

        data = result.data
        if data.get("pass"):
            await self.store.set_match_status(startup_id, partner_id, "draft_ready")
            log.info("verified", partner_id=partner_id)
            await self.store.complete_and_fanout(
                job_id=job_id, saga_id=saga_id, event_kind="Verified",
                event_payload={"partner_id": partner_id}, saga_step="verify",
                next_jobs=[], trace_id=job["trace_id"],
            )
            remaining = await self.store.count_active_jobs(saga_id, outreach.OUTREACH_STAGES)
            if remaining == 0:
                await self.store.set_saga_status(saga_id, "done", current_step="verify")
                log.info("outreach_saga_done", saga_id=saga_id)
            return

        # rejected — route feedback into a draft retry (R5), bounded by MAX_ATTEMPTS
        draft_job = await self.store.get_job_row(saga_id, "draft", partner_id)
        feedback = {"partner_id": partner_id, "issues": data.get("issues") or [],
                    "checks": data.get("checks")}
        if draft_job and (draft_job["attempts"] or 0) >= config.MAX_ATTEMPTS:
            log.warning("draft_dead_letter", partner_id=partner_id,
                        attempts=draft_job["attempts"])
            await self.store.dead_letter(
                job_ids=[job_id, draft_job["id"]], saga_id=saga_id,
                event_payload=feedback, trace_id=job["trace_id"],
            )
        else:
            log.info("verify_rejected_retry", partner_id=partner_id,
                     issues=feedback["issues"])
            await self.store.reject_and_rearm(
                verify_job_id=job_id, draft_job_id=draft_job["id"], saga_id=saga_id,
                feedback=feedback, trace_id=job["trace_id"],
            )

    async def _drain_monitor(self) -> None:
        """--drain: stop once no onboarding job is ready/leased (queue emptied).
        Safe because finish_stage enqueues the next stage in the same transaction
        that completes the current one — there is no zero-work window mid-saga."""
        while not self._stop.is_set():
            try:
                await asyncio.wait_for(self._stop.wait(), 1.0)
                return
            except asyncio.TimeoutError:
                pass
            n = await self.store.pool.fetchval(
                "SELECT count(*) FROM jobs WHERE stage = ANY($1::text[]) "
                "AND status IN ('ready', 'leased')",
                self._all_stages,
            )
            if n == 0:
                log.info("drain_complete")
                self.request_stop()
                return

    async def run(self, *, drain: bool = False) -> None:
        await self.reconcile_on_boot()
        coros = [self._reclaim_loop(), self._schedule_loop()]
        if drain:
            coros.append(self._drain_monitor())
        await asyncio.gather(*coros)

    def request_stop(self) -> None:
        self._stop.set()


async def main() -> None:
    import sys
    drain = "--drain" in sys.argv
    telemetry.configure()
    store = await Store.connect()
    sup = Supervisor(store, boot_epoch=os.environ.get("BOOT_EPOCH") or uuid.uuid4().hex)

    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, sup.request_stop)

    log.info("supervisor_starting", boot_epoch=sup.boot_epoch, drain=drain)
    try:
        await sup.run(drain=drain)
    finally:
        await store.close()


if __name__ == "__main__":
    asyncio.run(main())
