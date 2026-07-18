"""P1 — the gate rejects garbage (deterministic, pure, no DB/LLM).

The five adversarial cases the gate MUST resolve correctly. Because the gate is pure
spine logic, the agent that produced a candidate can never influence its own verdict.

  G1  worse matcher (flips stages)          -> REJECT (no improvement)
  G2  hallucinated datum, zero sources      -> REJECT (noise, drags score)
  G3  mirror-stuffed (10 URLs, 1 origin)    -> REJECT (independence stays 1)
  G4  improves bench, regresses held-out    -> REJECT (held-out guard)
  G5  correct AND >=2 independent origins   -> PROMOTE (control — not a reject-all)
"""
from apps.matchmaker.selfimprove import Datum, independent_origins, origin_key
from apps.matchmaker.selfimprove.gate import Decision, gate, round_score

# Frozen gold: three benchmark entities + one held-out, one field (funding_stage).
GOLD_BENCH = {"s1": "series_a", "s2": "seed", "s3": "series_b"}
GOLD_HELD = {"h1": "seed"}

# Two genuinely independent origins agreeing.
GOOD_SOURCES = ["https://crunchbase.com/x", "https://techinasia.com/y"]


def _grounded(gold: dict[str, str]) -> dict[str, Datum]:
    """A correct, independently grounded value-set for every entity in ``gold``."""
    return {eid: Datum(eid, val, list(GOOD_SOURCES)) for eid, val in gold.items()}


# --- origin normalization: the anti-echo-chamber primitive -------------------

def test_origin_key_collapses_mirrors_and_www():
    assert origin_key("https://www.crunchbase.com/org/x") == "crunchbase.com"
    assert origin_key("http://a.b.crunchbase.com/y?z=1") == "crunchbase.com"
    assert origin_key("https://startup.gov.vn/notice") == "startup.gov.vn"


def test_ten_mirrors_count_as_one_origin():
    mirrors = [f"https://m{i}.crunchbase.com/org/x" for i in range(10)]
    assert independent_origins(mirrors) == 1
    assert independent_origins(GOOD_SOURCES) == 2


# --- the incumbent baseline the candidates must beat -------------------------

def _incumbent_scores():
    """A modest but grounded incumbent: 2/3 bench correct, held-out correct."""
    inc_bench = {
        "s1": Datum("s1", "series_a", list(GOOD_SOURCES)),   # correct + grounded
        "s2": Datum("s2", "seed", list(GOOD_SOURCES)),        # correct + grounded
        # s3 left unfilled -> scores 0, not noise
    }
    inc_held = _grounded(GOLD_HELD)
    return (round_score(inc_bench, GOLD_BENCH), round_score(inc_held, GOLD_HELD))


def _gate(cand_bench, cand_held=None):
    inc_b, inc_h = _incumbent_scores()
    return gate(
        candidate_bench=cand_bench,
        candidate_held_out=cand_held if cand_held is not None else _grounded(GOLD_HELD),
        gold_bench=GOLD_BENCH, gold_held_out=GOLD_HELD,
        incumbent_bench_score=inc_b, incumbent_held_out_score=inc_h,
    )


def test_G1_worse_matcher_rejected():
    # Flips s1/s2 to wrong stages — strictly worse than the incumbent.
    cand = {
        "s1": Datum("s1", "seed", list(GOOD_SOURCES)),
        "s2": Datum("s2", "series_a", list(GOOD_SOURCES)),
        "s3": Datum("s3", "series_b", list(GOOD_SOURCES)),
    }
    assert _gate(cand).decision is Decision.REJECT


def test_G2_zero_source_hallucination_rejected():
    # Correct-looking values but ASSERTED with no sources -> noise, cannot raise score.
    cand = {
        "s1": Datum("s1", "series_a", []),
        "s2": Datum("s2", "seed", []),
        "s3": Datum("s3", "series_b", []),   # would be "new" data, but ungrounded
    }
    assert _gate(cand).decision is Decision.REJECT


def test_G3_mirror_stuffing_rejected():
    # s3 filled with ten mirrors of ONE origin — looks corroborated, isn't.
    mirrors = [f"https://m{i}.crunchbase.com/x" for i in range(10)]
    cand = {
        "s1": Datum("s1", "series_a", list(GOOD_SOURCES)),
        "s2": Datum("s2", "seed", list(GOOD_SOURCES)),
        "s3": Datum("s3", "series_b", mirrors),   # indep==1 -> conf 0 + noise
    }
    res = _gate(cand)
    assert res.decision is Decision.REJECT


def test_G4_benchmark_gaming_rejected_on_held_out():
    # Improves the benchmark (fills s3 correctly + grounded) but poisons held-out.
    better_bench = _grounded(GOLD_BENCH)                       # 3/3 correct + grounded
    poisoned_held = {"h1": Datum("h1", "series_c", list(GOOD_SOURCES))}  # wrong on held-out
    assert _gate(better_bench, poisoned_held).decision is Decision.REJECT


def test_G5_correct_and_grounded_promoted():
    # The control: genuinely better (fills s3 correctly + grounded), held-out intact.
    cand = _grounded(GOLD_BENCH)
    res = _gate(cand)
    assert res.decision is Decision.PROMOTE
    assert res.bench_score > _incumbent_scores()[0]
