"""The metric + the promotion gate (P1) — deterministic spine logic.

``score_entity``/``round_score`` define what "better" means, and ``gate`` decides
promotion. Both are pure: the agent that produced a candidate cannot influence the
verdict (separation of powers — the party being scored never computes its own score).

The metric rewards values that are BOTH correct AND independently grounded:

    round_score = mean( correct * confidence )  -  lambda * noise_rate

  - ``correct``      : 1 if the produced value equals the frozen gold value, else 0
  - ``confidence``   : from the number of independent source origins (corroboration)
  - ``noise_rate``   : fraction of gold entities for which a value was ASSERTED with
                       fewer than 2 independent origins — an ungrounded assertion

This is the whole anti-gaming engine: guessing gold can't win (confidence stays 0),
mirror-stuffing can't win (independence stays 1 -> confidence 0 + noise penalty), and
inventing data actively lowers the score. A missing value simply scores 0 (it is not an
assertion, so it is not noise) — the loop is rewarded for grounding, not for filling.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum

from .corroboration import confidence, independent_origins


@dataclass(slots=True)
class Datum:
    """One produced value for the single field under test, with its sources.

    ``value`` is the produced value (e.g. "series_a"); ``sources`` are the raw source
    strings/URLs it was drawn from. Independence and confidence derive from the sources.
    """
    entity_id: str
    value: str
    sources: list[str] = field(default_factory=list)

    @property
    def indep(self) -> int:
        return independent_origins(self.sources)

    def conf(self, k: int = 3) -> float:
        return confidence(self.indep, k)

    @property
    def is_noise(self) -> bool:
        """An asserted value with fewer than 2 independent origins is untrusted noise."""
        return self.indep < 2


def score_entity(produced: Datum | None, gold_value: str, k: int = 3) -> float:
    """Confidence-weighted correctness for one entity. Missing -> 0."""
    if produced is None:
        return 0.0
    return produced.conf(k) if produced.value == gold_value else 0.0


def round_score(produced: dict[str, Datum], gold: dict[str, str], *,
                lam: float = 0.5, k: int = 3) -> float:
    """Aggregate score of a produced value-set against the frozen gold values.

    ``produced`` maps entity_id -> Datum (may omit entities the pipeline couldn't fill);
    ``gold`` maps entity_id -> corroborated gold value for every benchmark entity.
    """
    n = len(gold)
    if n == 0:
        return 0.0
    total = sum(score_entity(produced.get(eid), gv, k) for eid, gv in gold.items())
    noise = sum(1 for eid in gold if (d := produced.get(eid)) is not None and d.is_noise)
    return total / n - lam * (noise / n)


class Decision(Enum):
    PROMOTE = "promote"
    REJECT = "reject"


@dataclass(slots=True)
class GateResult:
    decision: Decision
    reason: str
    bench_score: float
    held_out_score: float


def gate(*, candidate_bench: dict[str, Datum], candidate_held_out: dict[str, Datum],
         gold_bench: dict[str, str], gold_held_out: dict[str, str],
         incumbent_bench_score: float, incumbent_held_out_score: float,
         lam: float = 0.5, k: int = 3, eps: float = 1e-3) -> GateResult:
    """Promote the candidate over the incumbent iff it STRICTLY improves the benchmark
    and does not regress the held-out slice. Pure function — un-gameable by the agent.

    Grounding is enforced implicitly by ``round_score``: zero-source and mirror-only
    data score 0 and incur the noise penalty, so garbage candidates fail on the numbers
    rather than on a special case.
    """
    s_new = round_score(candidate_bench, gold_bench, lam=lam, k=k)
    s_held = round_score(candidate_held_out, gold_held_out, lam=lam, k=k)

    if s_held < incumbent_held_out_score - eps:
        return GateResult(Decision.REJECT, "regressed held-out", s_new, s_held)
    if s_new <= incumbent_bench_score + eps:
        return GateResult(Decision.REJECT, "no improvement", s_new, s_held)
    return GateResult(Decision.PROMOTE, "improved + grounded + no regression", s_new, s_held)
