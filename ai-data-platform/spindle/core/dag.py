"""DAG advance + on_reject — pure saga-graph decisions (spec §D.3, Seam 2).

Given a manifest saga (an ordered stage list) and the stage that just landed,
compute the next stage; given an `on_reject` edge and the current attempt count,
decide retry vs dead-letter. This replaces the hardcoded `next_stage` map and the
hand-rolled reject→retry loop in today's supervisor with data-driven logic.

Pure: operates on the `Stage`/`Saga`/`OnReject` dataclasses the manifest loader
already produces (`spindle.manifest.loader`). No I/O, no `asyncpg`.
"""
from __future__ import annotations

from typing import Literal

from spindle.manifest.loader import OnReject, Saga, Stage


def next_stage(saga: Saga, current: str) -> Stage | None:
    """Return the stage after ``current`` in the ordered saga, or ``None`` if
    ``current`` is the last stage. Raises ``KeyError`` if ``current`` is not in
    the saga (a manifest/dispatch mismatch — fail loud, don't skip silently)."""
    stages = saga.stages
    for i, s in enumerate(stages):
        if s.stage == current:
            return stages[i + 1] if i + 1 < len(stages) else None
    raise KeyError(f"stage {current!r} not in saga {saga.name!r}")


RejectAction = Literal["retry", "dead"]


def on_reject_action(edge: OnReject | None, attempts: int) -> tuple[RejectAction, str]:
    """Decide what a rejected stage does, from its declarative ``on_reject`` edge.

    ``attempts`` is the *retry-target* job's attempt count so far. Returns
    ``("retry", <stage>)`` while under budget, else ``("dead", <then>)``. With no
    edge, the stage has no retry policy → dead-letter immediately.
    """
    if edge is None:
        return ("dead", "dead")
    if attempts < edge.max:
        return ("retry", edge.retry)
    return ("dead", edge.then)
