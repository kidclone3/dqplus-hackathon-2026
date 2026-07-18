"""Generic, manifest-driven supervisor — the reconciler (spec §5.2, §5.3, §D).

Postgres is the source of truth for desired + leased state; the supervisor is a
reconciler, not the record. This is the domain-agnostic descendant of the old
``spine.supervisor``: the four §D changes make it read everything from loaded app
manifests instead of hardcoding deal-flow stage names.

  1. Scheduler is stage-name-agnostic: a leased job carries its ``app_id``; the
     supervisor resolves ``stage → {run, port?}`` from that app's manifest.
     ``run: code`` calls the ``@stage`` fn; ``run: <agent>`` runs the pooled
     worker then hands ``RpcResult.data`` to the ``@agent_stage`` handler's
     ``validate``/``persist_and_advance`` (Seam 1).
  2. The DAG engine reads the ordered saga from the manifest (``core.dag``): the
     next stage, per-target fan-out (``next_jobs``), and the ``on_reject`` retry
     edge are generic — per-target fan-out and reject→rearm→dead-letter are
     handler/DAG behaviour, not special cases (Seam 2).
  3. Pools are keyed by ``(runtime, skill, model)`` — the union of every app's
     ``AgentSpec``s, deduped by pool key, with tool/model compatibility validated
     at load (mismatch = hard manifest error, risk R-a).
  4. ``app_id`` is threaded through reconcile / LISTEN-NOTIFY wake / reclaim /
     dead-letter — the crash-recovery core is otherwise unchanged.

Entrypoint: ``python -m spindle.app.supervisor`` (R4).
"""
from __future__ import annotations

import asyncio
import importlib
import os
import signal
import sys
import uuid
from dataclasses import dataclass
from pathlib import Path

from spine import config, telemetry
from spine import transport
from spine.transport import LocalProcessLauncher, ProcessDied, RpcResult
from spindle import registry
from spindle.adapters.postgres_store import PostgresStore
from spindle.core import dag
from spindle.manifest.loader import Manifest, Stage, load_manifest
from spindle.app.context import Advance, Reject, StageCtx

log = telemetry.get_logger("supervisor")

_REPO_ROOT = Path(__file__).resolve().parents[2]


class ManifestError(RuntimeError):
    """A manifest is internally inconsistent (e.g. incompatible shared pool)."""


@dataclass(slots=True)
class _App:
    """A loaded app: its manifest + the flat stage index the dispatcher uses."""

    manifest: Manifest
    stages: dict[str, Stage]           # stage name -> Stage (unique across sagas)
    all_stage_names: tuple[str, ...]


def _discover_manifests(app_dirs: list[str] | None) -> list[Manifest]:
    """Load every app manifest. Default: discover ``apps/*/app.yaml`` (generic —
    the platform hosts whatever apps are present, no app named in code)."""
    if app_dirs is None:
        paths = sorted((_REPO_ROOT / "apps").glob("*/app.yaml"))
    else:
        paths = [Path(d) if str(d).endswith((".yaml", ".yml")) else Path(d) / "app.yaml"
                 for d in app_dirs]
    return [load_manifest(p) for p in paths]


class Supervisor:
    def __init__(self, store, *, boot_epoch: str | None = None,
                 reclaim_interval: float = 3.0,
                 launcher: LocalProcessLauncher | None = None,
                 app_dirs: list[str] | None = None,
                 stages: list[str] | None = None):
        self.store = store                                # app-facing store (handlers)
        self._plat = PostgresStore(store.pool)            # platform store (app_id-scoped)
        self.boot_epoch = boot_epoch or uuid.uuid4().hex
        self.reclaim_interval = reclaim_interval
        if launcher is None:
            scratch = os.path.join(os.getcwd(), ".agent-scratch")
            os.makedirs(scratch, exist_ok=True)
            launcher = LocalProcessLauncher(cwd=scratch)
        self.launcher = launcher

        manifests = _discover_manifests(app_dirs)
        self.apps: dict[str, _App] = {}
        for m in manifests:
            stage_map = {s.stage: s for saga in m.sagas.values() for s in saga.stages}
            names = tuple(sorted(stage_map))
            self.apps[m.app_id] = _App(m, stage_map, names)
        self._load_plugins(manifests)
        self._stage_specs = self._build_pools(manifests)  # (app_id, stage) -> AgentSpec

        # `stages` restricts the run to a subset (e.g. scripts/cleanup.py drains
        # only a cleanup saga without leasing stale jobs from other sagas).
        self._all_stages = (sorted(stages) if stages else
                            sorted({n for a in self.apps.values() for n in a.all_stage_names}))
        self._sem = asyncio.Semaphore(config.MAX_CONCURRENCY)
        self._stop = asyncio.Event()

    # ---------------------------------------------------------------- load-time

    @staticmethod
    def _load_plugins(manifests: list[Manifest]) -> None:
        """Import each app's plugin so its ``@stage``/``@agent_stage``/``@port``
        register. Idempotent across supervisor rebuilds: clear the registry, then
        (re)load each plugin so the registration survives a prior ``registry.clear``
        (e.g. from a unit test) — module-level decorators only run on first import."""
        registry.clear()
        for m in manifests:
            mod = sys.modules.get(m.plugin)
            if mod is None:
                importlib.import_module(m.plugin)
            else:
                importlib.reload(mod)

    def _build_pools(self, manifests: list[Manifest]) -> dict[tuple[str, str], transport.AgentSpec]:
        """Union every app's agent stages, keyed by ``(runtime, skill, model)``.
        Two stages sharing a pool key MUST agree on tools + model, else the shared
        worker would be launched two incompatible ways — a hard manifest error
        (risk R-a). Returns the per-(app, stage) transport spec used to launch."""
        pool_profile: dict[tuple, tuple[frozenset, str]] = {}
        specs: dict[tuple[str, str], transport.AgentSpec] = {}
        for m in manifests:
            for saga in m.sagas.values():
                for st in saga.stages:
                    if st.is_code:
                        continue
                    agent = m.agents.get(st.run)
                    if agent is None:
                        raise ManifestError(
                            f"{m.app_id}: stage {st.stage!r} run={st.run!r} names no agent")
                    model = agent.model or config.AGENT_MODEL
                    key = (agent.runtime, agent.skill, model)
                    tools = frozenset(agent.tools)
                    prev = pool_profile.get(key)
                    if prev is None:
                        pool_profile[key] = (tools, model)
                    elif prev != (tools, model):
                        raise ManifestError(
                            f"shared pool {key} has incompatible tool/model allowlists: "
                            f"{prev} vs {(tools, model)}")
                    specs[(m.app_id, st.stage)] = transport.AgentSpec(
                        name=st.run, runtime=agent.runtime, skill=agent.skill,
                        stage=st.stage, tools=list(agent.tools),
                        pool_size=agent.pool_size, model=model,
                    )
        return specs

    # ---------------------------------------------------------------- reconcile

    async def reconcile_on_boot(self) -> None:
        """Prior-epoch workers are orphans → mark dead and reclaim their leases.
        Workers are the SHARED control plane (not app-scoped); lease reclaim runs
        across all apps (``app_id=None``)."""
        async with self._plat.pool.acquire() as conn:
            orphans = await conn.fetch(
                "SELECT worker_id, pid FROM workers "
                "WHERE status <> 'dead' AND boot_epoch <> $1", self.boot_epoch,
            )
            if orphans:
                await conn.execute(
                    "UPDATE workers SET status = 'dead' "
                    "WHERE status <> 'dead' AND boot_epoch <> $1", self.boot_epoch,
                )
        reclaimed = await self._plat.reclaim_expired_leases(app_id=None)
        log.info("reconcile_on_boot", boot_epoch=self.boot_epoch,
                 orphans=len(orphans), leases_reclaimed=reclaimed)

    async def _reclaim_loop(self) -> None:
        while not self._stop.is_set():
            n = await self._plat.reclaim_expired_leases(app_id=None)
            if n:
                log.info("leases_reclaimed", count=n)
            try:
                await asyncio.wait_for(self._stop.wait(), self.reclaim_interval)
            except asyncio.TimeoutError:
                pass

    async def _schedule_loop(self) -> None:
        """Competing-consumer scheduler: lease any app's ready job (pools are
        shared, ``app_id=None``) and dispatch it. Woken by LISTEN/NOTIFY; polls as
        a fallback. The wake carries the stage; the shared scheduler serves every
        app off the one channel."""
        wake = asyncio.Event()
        conn = await self._plat.listen(lambda _payload: wake.set())
        active: set[asyncio.Task] = set()
        try:
            while not self._stop.is_set():
                if len(active) >= config.MAX_CONCURRENCY:
                    await asyncio.sleep(0.1)
                    continue
                job = await self._plat.acquire_job(
                    worker_id=f"sup:{self.boot_epoch}", stages=self._all_stages,
                    app_id=None,
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
            await self._plat.pool.release(conn)

    # ---------------------------------------------------------------- dispatch

    async def _dispatch(self, job) -> None:
        """Resolve ``stage → {run, port?}`` from the leased job's app manifest and
        run it. Code stages call the ``@stage`` fn in-process; agent stages run the
        pooled worker then hand the result to the ``@agent_stage`` handler."""
        job_id, app_id, stage = job["id"], job["app_id"], job["stage"]
        telemetry.bind(job_id=job_id, saga_id=job["saga_id"],
                       trace_id=job["trace_id"], stage=stage)
        try:
            app = self.apps.get(app_id)
            if app is None or stage not in app.stages:
                log.warning("unknown_stage", app_id=app_id, stage=stage)
                await self._plat.fail_job(job_id)
                return
            stage_obj = app.stages[stage]
            saga_row = await self._plat.get_saga(app_id, job["saga_id"])
            saga_def = app.manifest.sagas[saga_row["type"]] if saga_row else None
            ctx = StageCtx(
                app_id=app_id, saga_id=job["saga_id"],
                subject_id=saga_row["subject_id"] if saga_row else None,
                target_id=job["target_id"], trace_id=job["trace_id"],
                attempts=job["attempts"] or 0,
                retry_feedback=self._feedback(job), store=self.store,
            )
            if stage_obj.is_code:
                fn = registry.get_stage(stage)
                outcome = await fn(ctx)
                await self._apply_advance(job, stage_obj, saga_def, outcome)
            else:
                await self._run_agent_stage(job, stage_obj, saga_def, ctx)
        except ProcessDied as e:
            log.warning("agent_process_died", error=str(e))
            await self._plat.fail_job(job_id)
        except Exception as e:
            log.error("dispatch_error", error=repr(e))
            await self._plat.fail_job(job_id)
        finally:
            telemetry.clear()

    @staticmethod
    def _feedback(job) -> dict | None:
        fb = job.get("verify_feedback") if hasattr(job, "get") else None
        if isinstance(fb, str):
            import json as _json
            return _json.loads(fb)
        return fb

    async def _run_agent_stage(self, job, stage_obj: Stage, saga_def, ctx: StageCtx) -> None:
        """``run: <agent>``: build prompt → run pooled worker → validate (R3) →
        persist_and_advance. A rejected result (bad schema) re-arms the job; a
        handler-signalled :class:`Reject` routes through the ``on_reject`` edge."""
        handler = registry.get_agent_stage(stage_obj.stage)()
        spec = self._stage_specs[(ctx.app_id, stage_obj.stage)]
        prompt = await handler.build_prompt(ctx)
        result = await self._run_worker(spec, prompt, job)
        if not result.success or not handler.validate(result.data):
            status = await self._plat.fail_job(job["id"], max_attempts=config.MAX_ATTEMPTS)
            log.warning("agent_reject", stage=stage_obj.stage, new_status=status,
                        stop_reason=result.stop_reason, error=result.error_message)
            return
        outcome = await handler.persist_and_advance(ctx, result.data)
        if isinstance(outcome, Reject):
            await self._apply_reject(job, stage_obj, outcome)
        else:
            await self._apply_advance(job, stage_obj, saga_def, outcome)

    async def _run_worker(self, spec, prompt: str, job) -> RpcResult:
        """Spawn a fresh RPC process, run one prompt, record usage, kill it (R7
        session hygiene: N=1, no warm-context bleed). Unchanged from the pre-split
        supervisor; the control-plane writes go through the platform store."""
        job_id = job["id"]
        worker_id = f"{spec.name}:{self.boot_epoch}:{job_id}"
        async with self._sem:
            ch = await self.launcher.spawn(spec, worker_id)
            pid = ch._proc.pid if ch._proc else None
            await self._plat.register_worker(
                worker_id, agent_type=spec.name, runtime=spec.runtime,
                boot_epoch=self.boot_epoch, pid=pid, status="busy",
                current_job_id=job_id,
            )
            log.info("agent_prompt", worker_id=worker_id, target_id=job["target_id"])
            try:
                result = await ch.prompt(prompt, timeout=config.AGENT_TIMEOUT)
            finally:
                await ch.close()
                await self._plat.set_worker_status(worker_id, "dead")

        for u in result.usages:
            await self._plat.record_usage(
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

    # ---------------------------------------------------------------- DAG engine

    async def _apply_advance(self, job, stage_obj: Stage, saga_def, adv: Advance) -> None:
        """Complete the job + append the milestone event + fold the saga + enqueue
        the next manifest stage over ``adv.next_targets`` — one transaction. When
        nothing is enqueued (terminal stage, or an empty fan-out branch), the saga
        is done once no active job remains (fan-in on a terminal stage)."""
        app_id, saga_id = job["app_id"], job["saga_id"]
        target, trace = job["target_id"], job["trace_id"]
        nxt = dag.next_stage(saga_def, stage_obj.stage) if saga_def else None
        if nxt is None:
            next_jobs: list[dict] = []
        else:
            targets = adv.next_targets if adv.next_targets is not None else [target]
            next_agent = None if nxt.is_code else nxt.run
            next_jobs = [{"stage": nxt.stage, "target_id": t, "agent": next_agent}
                         for t in targets]
        saga_step = nxt.stage if (nxt is not None and next_jobs) else stage_obj.stage
        await self._plat.complete_and_fanout(
            app_id, job_id=job["id"], saga_id=saga_id, event_kind=adv.event_kind,
            event_payload=adv.event_payload, saga_step=saga_step,
            next_jobs=next_jobs, saga_status="running", trace_id=trace,
        )
        if not next_jobs and saga_def is not None:
            remaining = await self._plat.count_active_jobs(
                app_id, saga_id, list(saga_def.stage_names))
            if remaining == 0:
                await self._plat.set_saga_status(
                    app_id, saga_id, "done", current_step=stage_obj.stage)

    async def _apply_reject(self, job, stage_obj: Stage, rej: Reject) -> None:
        """Route a rejected agent result through the stage's declarative
        ``on_reject`` edge: rearm the retry stage's sub-job with feedback while
        under budget, else dead-letter both (Seam 2). Generic — the old hand-rolled
        reject loop is gone; the store's ``reject_and_rearm`` primitive is fully
        stage-name-agnostic (``reject_job_id``/``retry_job_id``/``retry_stage``)."""
        app_id, saga_id = job["app_id"], job["saga_id"]
        target, trace = job["target_id"], job["trace_id"]
        edge = stage_obj.on_reject
        retry_job = None
        if edge is not None:
            retry_job = await self._plat.get_job_row(app_id, saga_id, edge.retry, target)
        attempts = (retry_job["attempts"] or 0) if retry_job else 0
        action, _dest = dag.on_reject_action(edge, attempts)
        if action == "retry" and retry_job is not None:
            log.info("stage_rejected_retry", stage=stage_obj.stage, target_id=target)
            await self._plat.reject_and_rearm(
                app_id, reject_job_id=job["id"], retry_job_id=retry_job["id"],
                retry_stage=edge.retry, saga_id=saga_id, feedback=rej.feedback,
                trace_id=trace,
            )
        else:
            ids = [job["id"]] + ([retry_job["id"]] if retry_job else [])
            log.warning("stage_dead_letter", stage=stage_obj.stage, target_id=target)
            await self._plat.dead_letter(
                app_id, job_ids=ids, saga_id=saga_id,
                event_payload=rej.feedback, trace_id=trace,
            )

    # ---------------------------------------------------------------- run loop

    async def _drain_monitor(self) -> None:
        """--drain: stop once no job is ready/leased (queue emptied). Safe because
        the advance enqueues the next stage in the same transaction that completes
        the current one — there is no zero-work window mid-saga."""
        while not self._stop.is_set():
            try:
                await asyncio.wait_for(self._stop.wait(), 1.0)
                return
            except asyncio.TimeoutError:
                pass
            n = await self._plat.pool.fetchval(
                "SELECT count(*) FROM jobs WHERE stage = ANY($1::text[]) "
                "AND status IN ('ready', 'leased')", self._all_stages,
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
    import asyncpg

    drain = "--drain" in sys.argv
    telemetry.configure()
    # Build the app-facing store generically: load each app's plugin so its store
    # factory registers, then construct it from a shared pool — no app named here.
    manifests = _discover_manifests(None)
    Supervisor._load_plugins(manifests)
    pool = await asyncpg.create_pool(config.DATABASE_URL)
    store = registry.get_app_store()(pool)
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
