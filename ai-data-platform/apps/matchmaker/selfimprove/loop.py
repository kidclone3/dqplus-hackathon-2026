"""The self-improvement loop (P2) — observe -> propose -> gate, N rounds, unattended.

``run_loop`` wraps the P1 ``gate`` in a promotion loop. Each round a ``Proposer`` returns
a full candidate value-set (a "version"); the gate promotes it only if it beats the
current incumbent without regressing held-out. The returned curve of scores is the P2
evidence: it rises only when the proposer finds correct + independently grounded values.

The ``Proposer`` seam is where the real pi/feynman agent drops in. Its signature is
deterministic and side-effect free from the loop's perspective:

    proposer(round_idx, incumbent_bench) -> Candidate

so a live agent (reads logs, fetches sources, corroborates) and a simulated proposer
(used by the P2 test to prove the mechanism) are interchangeable — the gate never
changes. A round whose candidate is a hallucination is rejected in place: the incumbent
is retained and the score does not jump, which is exactly the safety property to show.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable

from .gate import Datum, Decision, gate, round_score


@dataclass(slots=True)
class Candidate:
    """A proposed version: the value-set it produces on the benchmark and held-out slices."""
    bench: dict[str, Datum] = field(default_factory=dict)
    held_out: dict[str, Datum] = field(default_factory=dict)


# round_idx (0-based), current incumbent bench value-set -> next candidate to try.
Proposer = Callable[[int, dict[str, Datum]], Candidate]


@dataclass(slots=True)
class RoundResult:
    round: int
    decision: Decision
    reason: str
    bench_score: float       # incumbent score AFTER this round (post promote/reject)
    held_out_score: float
    promoted: bool


def run_loop(*, gold_bench: dict[str, str], gold_held_out: dict[str, str],
             proposer: Proposer, rounds: int,
             lam: float = 0.5, k: int = 3, eps: float = 1e-3) -> list[RoundResult]:
    """Run the gated improvement loop for ``rounds`` rounds. Returns one result per round.

    Starts from an empty incumbent (score 0). The incumbent advances only on PROMOTE, so
    a rejected round leaves the score flat — the curve reflects real, gated progress.
    """
    inc_bench: dict[str, Datum] = {}
    inc_held: dict[str, Datum] = {}
    inc_bench_score = round_score(inc_bench, gold_bench, lam=lam, k=k)
    inc_held_score = round_score(inc_held, gold_held_out, lam=lam, k=k)

    results: list[RoundResult] = []
    for i in range(rounds):
        cand = proposer(i, inc_bench)
        res = gate(
            candidate_bench=cand.bench, candidate_held_out=cand.held_out,
            gold_bench=gold_bench, gold_held_out=gold_held_out,
            incumbent_bench_score=inc_bench_score, incumbent_held_out_score=inc_held_score,
            lam=lam, k=k, eps=eps,
        )
        promoted = res.decision is Decision.PROMOTE
        if promoted:
            inc_bench, inc_held = cand.bench, cand.held_out
            inc_bench_score, inc_held_score = res.bench_score, res.held_out_score
        results.append(RoundResult(
            round=i, decision=res.decision, reason=res.reason,
            bench_score=inc_bench_score, held_out_score=inc_held_score, promoted=promoted,
        ))
    return results
