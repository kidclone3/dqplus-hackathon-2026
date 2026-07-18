"""Ports — the structural seams the platform core depends on (spec §E).

These are `Protocol`s, not base classes: the core imports *these* and nothing
else at the I/O edge, so it can run against a fake in unit tests. Adapters
(`spindle/adapters/*`) satisfy them structurally without importing this module.

Ports exist for **testability and real second-adapters**, not imaginary DB
portability. The `Store` port is honestly Postgres-shaped: it exposes the
lease/advance/reclaim verbs that make crash-recovery correct, not a generic
`find_all()`/`save()` repository (spec §E).

Pure module: stdlib + typing only. Imports no adapter and no `asyncpg`.
"""
from __future__ import annotations

from typing import Any, Awaitable, Callable, Protocol, Sequence, runtime_checkable


@runtime_checkable
class Store(Protocol):
    """Platform store: jobs/events/sagas/artifacts, every row scoped by `app_id`.

    Postgres-shaped on purpose (spec §E). The single-transaction advance methods
    (`finish_stage`/`complete_and_fanout`/`reject_and_rearm`/`dead_letter`) write
    **only** platform rows — never app tables — preserving the one-txn
    event+job+saga write that is the crash-recovery story (R5/R6).
    """

    # ---- artifacts (generic blackboard) ----
    async def record_artifact(self, app_id: str, saga_id: str, step: str, payload: dict,
                              *, entity_id: str | None = ..., target_id: str = ...,
                              trace_id: str | None = ...) -> None: ...

    async def get_artifact(self, app_id: str, saga_id: str, step: str,
                           target_id: str = ...) -> dict | None: ...

    # ---- events (append-only source of truth) ----
    async def record_event(self, app_id: str, saga_id: str, seq: int, kind: str,
                           payload: dict | None = ..., *,
                           trace_id: str | None = ...) -> None: ...

    # ---- jobs (the queue) ----
    async def enqueue_job(self, app_id: str, saga_id: str, stage: str, *,
                          target_id: str = ..., agent: str | None = ...,
                          input_ref: dict | None = ..., trace_id: str | None = ...) -> int | None: ...

    async def acquire_job(self, worker_id: str, stages: Sequence[str], *,
                          app_id: str | None = ..., lease_seconds: int | None = ...) -> Any | None: ...

    async def reclaim_expired_leases(self, *, app_id: str | None = ...) -> int: ...

    async def complete_job(self, job_id: int) -> None: ...

    async def fail_job(self, job_id: int, *, max_attempts: int = ...) -> str: ...

    # ---- sagas (folded projection) ----
    async def create_saga(self, app_id: str, saga_id: str, type_: str, subject_id: str | None,
                          *, current_step: str | None = ..., trace_id: str | None = ...) -> None: ...

    async def finish_stage(self, app_id: str, *, job_id: int, saga_id: str, event_kind: str,
                           saga_step: str, **kwargs: Any) -> None: ...

    async def complete_and_fanout(self, app_id: str, *, job_id: int, saga_id: str,
                                  event_kind: str, event_payload: dict | None, saga_step: str,
                                  next_jobs: list[dict], **kwargs: Any) -> None: ...

    async def get_saga(self, app_id: str, saga_id: str) -> dict | None: ...


@runtime_checkable
class RuntimeLauncher(Protocol):
    """Spawns an agent runtime for one job (spec §E; mirrors transport.py).

    Two real adapters justify the port: `LocalProcessLauncher` (host now) and a
    future `ContainerLauncher` — the host→container isolation seam.
    """

    async def spawn(self, spec: Any, worker_id: str) -> Any: ...


@runtime_checkable
class Notifier(Protocol):
    """The LISTEN/NOTIFY edge, isolated so the core stays deterministic.

    `PgNotifier` (Postgres `LISTEN/NOTIFY`) is the real adapter.
    """

    async def notify(self, channel: str, payload: str) -> None: ...

    async def listen(self, callback: Callable[[str], Awaitable[None] | None]) -> Any: ...


@runtime_checkable
class Clock(Protocol):
    """The wall-clock edge, isolated so time-dependent core logic is testable.

    `SystemClock` is the real adapter; tests inject a fake.
    """

    def now(self) -> float: ...
