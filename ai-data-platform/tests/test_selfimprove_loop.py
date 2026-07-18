"""P2 — the loop climbs unattended, and the gate catches a hallucination mid-run.

A simulated proposer stands in for the live pi/feynman agent (same ``Proposer`` seam).
Round by round it grounds one more benchmark entity with 2+ independent origins, so the
gated score rises monotonically. On one designated round it instead proposes a
zero-source hallucination that would LOOK like progress; the gate must reject it, leaving
the score flat that round. That rejection event is the demo's whole argument: the number
goes up only because the system got more right, never because it learned to fill fields.
"""
from apps.matchmaker.selfimprove import Datum, run_loop
from apps.matchmaker.selfimprove.gate import Decision

GOLD_BENCH = {"s1": "series_a", "s2": "seed", "s3": "series_b", "s4": "seed"}
GOLD_HELD = {"h1": "seed", "h2": "series_a"}
# 3 independent origins -> full confidence (K=3), so a grounded entity scores ~1.0.
SRC = ["https://crunchbase.com/x", "https://techinasia.com/y", "https://dealstreetasia.com/z"]

# Order in which the honest proposer grounds benchmark entities.
_FILL_ORDER = ["s1", "s2", "s3", "s4"]
_HALLUCINATION_ROUND = 2   # on this round the proposer tries to cheat


def _held_grounded() -> dict[str, Datum]:
    return {eid: Datum(eid, val, list(SRC)) for eid, val in GOLD_HELD.items()}


def simulated_proposer(round_idx: int, incumbent_bench: dict[str, Datum]):
    """Honest most rounds; on the hallucination round, cheats with zero-source data."""
    from apps.matchmaker.selfimprove import Candidate

    cand_bench = dict(incumbent_bench)  # build on what's already promoted

    if round_idx == _HALLUCINATION_ROUND:
        # Fill EVERY remaining entity with correct-looking values but NO sources.
        for eid, val in GOLD_BENCH.items():
            cand_bench.setdefault(eid, Datum(eid, val, []))
        return Candidate(bench=cand_bench, held_out=_held_grounded())

    # Honest round: ground the next unfilled entity with 2 independent origins.
    honest_idx = round_idx if round_idx < _HALLUCINATION_ROUND else round_idx - 1
    if honest_idx < len(_FILL_ORDER):
        eid = _FILL_ORDER[honest_idx]
        cand_bench[eid] = Datum(eid, GOLD_BENCH[eid], list(SRC))
    return Candidate(bench=cand_bench, held_out=_held_grounded())


def test_P2_loop_climbs_and_gate_catches_hallucination():
    results = run_loop(
        gold_bench=GOLD_BENCH, gold_held_out=GOLD_HELD,
        proposer=simulated_proposer, rounds=5,
    )
    scores = [r.bench_score for r in results]

    # 1. The hallucination round is REJECTED and leaves the score flat.
    hall = results[_HALLUCINATION_ROUND]
    assert hall.decision is Decision.REJECT
    assert hall.reason == "no improvement"
    assert scores[_HALLUCINATION_ROUND] == scores[_HALLUCINATION_ROUND - 1]

    # 2. The curve is monotonically non-decreasing (the gate never lets it drop).
    assert all(b >= a - 1e-9 for a, b in zip(scores, scores[1:]))

    # 3. It genuinely climbed from ~0 to a strong grounded score by the end.
    assert scores[0] > 0.0
    assert scores[-1] > scores[0]
    assert scores[-1] > 0.9  # all four entities correct + grounded -> near 1.0

    # 4. At least one honest promotion happened after the rejected round (loop recovers).
    assert any(r.promoted for r in results[_HALLUCINATION_ROUND + 1:])


def test_P2_pure_hallucination_proposer_never_climbs():
    """Sanity: a proposer that ONLY ever hallucinates (zero sources) stays at zero."""
    from apps.matchmaker.selfimprove import Candidate

    def liar(round_idx, incumbent_bench):
        bench = {eid: Datum(eid, val, []) for eid, val in GOLD_BENCH.items()}
        return Candidate(bench=bench, held_out=_held_grounded())

    results = run_loop(gold_bench=GOLD_BENCH, gold_held_out=GOLD_HELD,
                       proposer=liar, rounds=4)
    assert all(r.decision is Decision.REJECT for r in results)
    assert all(r.bench_score <= 0.0 for r in results)
