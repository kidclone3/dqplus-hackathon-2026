"""Unit tests for the pure platform core (spec §E). No DB, no I/O."""
from __future__ import annotations

import pytest

from spindle.core import dag, reconcile, saga
from spindle.manifest.loader import OnReject, Saga, Stage


def _outreach() -> Saga:
    return Saga(name="outreach", stages=(
        Stage(stage="filter", run="code"),
        Stage(stage="match", run="matcher", port="matcher"),
        Stage(stage="draft", run="drafter"),
        Stage(stage="verify", run="verifier",
              on_reject=OnReject(retry="draft", max=2, then="dead")),
    ))


def test_next_stage_advances_and_terminates():
    s = _outreach()
    assert dag.next_stage(s, "filter").stage == "match"
    assert dag.next_stage(s, "draft").stage == "verify"
    assert dag.next_stage(s, "verify") is None


def test_next_stage_rejects_unknown_stage():
    with pytest.raises(KeyError):
        dag.next_stage(_outreach(), "nope")


def test_on_reject_retry_then_dead():
    edge = OnReject(retry="draft", max=2, then="dead")
    assert dag.on_reject_action(edge, attempts=1) == ("retry", "draft")
    assert dag.on_reject_action(edge, attempts=2) == ("dead", "dead")
    assert dag.on_reject_action(None, attempts=0) == ("dead", "dead")


def test_next_seq_is_monotonic():
    assert saga.next_seq([]) == 1
    assert saga.next_seq([1, 2, 5]) == 6


def test_partition_orphans_by_epoch():
    workers = [
        {"worker_id": "a", "boot_epoch": "e1", "status": "busy"},
        {"worker_id": "b", "boot_epoch": "e0", "status": "busy"},
        {"worker_id": "c", "boot_epoch": "e0", "status": "dead"},
    ]
    survivors, orphans = reconcile.partition_orphans(workers, "e1")
    assert [w["worker_id"] for w in survivors] == ["a"]
    assert [w["worker_id"] for w in orphans] == ["b"]
