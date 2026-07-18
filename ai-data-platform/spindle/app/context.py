"""Stage context + advance results — the plugin↔platform contract (Seam 1/2).

A plugin's code-stage bodies (``@stage``) and agent-stage handlers
(``@agent_stage``) receive a :class:`StageCtx` and return a declarative advance
result the DAG engine applies. They never call the queue-advance transaction
themselves — they do the app-domain writes, then hand the platform a description
of where the saga goes next:

- :class:`Advance` — normal completion. ``next_targets`` names the targets the
  *next* manifest stage fans out over (``None`` → the current target, i.e. a
  linear step; ``[]`` → this branch ends). The DAG engine reads the next stage
  (and its agent) from the manifest — the handler never names it.
- :class:`Reject` — the agent result failed an app check. The DAG engine consults
  the stage's declarative ``on_reject`` edge to rearm-or-dead-letter.

This is why a per-target fan-out stage and a rejected stage's retry are not
special cases: they are ordinary ``Advance``/``Reject`` values (spec §D.3, Seam 2).
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from spindle import registry


@dataclass(slots=True)
class StageCtx:
    """What a stage body/handler sees. App-facing store + resolved saga identity.

    ``store`` is the app-facing store (domain tables + the generic artifact
    blackboard); ``app_id`` scopes the platform rows the supervisor writes around
    the handler. ``subject_id`` is the saga's subject while ``target_id`` is this
    job's target (e.g. one item in a fan-out) — they coincide for linear sagas.
    ``retry_feedback`` carries the payload a downstream rejection rearmed this job
    with (the generic ``jobs.verify_feedback`` column), ``None`` on a first run.
    """

    app_id: str
    saga_id: str
    subject_id: str | None
    target_id: str
    trace_id: str | None
    attempts: int
    retry_feedback: dict | None
    store: Any

    def port(self, name: str) -> Any:
        """Resolve a named, app-swappable component (the manifest ``ports:``)."""
        return registry.get_port(name)


@dataclass(slots=True, frozen=True)
class Advance:
    """Normal completion. The DAG engine enqueues the next manifest stage over
    ``next_targets`` (``None`` → ``[ctx.target_id]``; ``[]`` → no next job)."""

    event_kind: str
    event_payload: dict | None = None
    next_targets: list[str] | None = None


@dataclass(slots=True, frozen=True)
class Reject:
    """The agent result was rejected by an app check; route via ``on_reject``."""

    feedback: dict


class AgentStageHandler:
    """One handler per agent-backed stage (Seam 1). Instantiated per dispatch, so
    ``build_prompt`` may stash fetched state for ``persist_and_advance`` to reuse.

    The supervisor calls ``build_prompt`` → runs the pooled worker → ``validate``
    → ``persist_and_advance``. ``validate`` is the R3 schema gate; a ``False``
    re-arms the job (prompt strengthens on retry).
    """

    async def build_prompt(self, ctx: StageCtx) -> str:
        raise NotImplementedError

    def validate(self, data: Any) -> bool:
        raise NotImplementedError

    async def persist_and_advance(self, ctx: StageCtx, data: Any) -> Advance | Reject:
        raise NotImplementedError
