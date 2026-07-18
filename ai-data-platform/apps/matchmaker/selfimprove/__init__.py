"""Self-improvement loop (verification harness for the self-evolving-agents idea).

This package proves ONE falsifiable claim in the smallest possible form, on a single
match-driving field (``funding_stage``):

  P1 — the gate rejects garbage. A candidate is promoted ONLY when it beats the
       incumbent on a frozen benchmark AND does not regress a held-out slice AND every
       asserted datum is independently corroborated. Deterministic spine logic — the
       agent being scored can never compute its own verdict. See ``gate.py``.

  P2 — the loop climbs unattended. Wrapping the P1 gate in an observe->propose->gate
       loop over N rounds, the score trends up only when the proposer finds values that
       are BOTH correct AND independently grounded. See ``loop.py``.

Why it can't lie to itself (the through-line of the whole design):
  - correctness is confidence-weighted, and confidence comes from the number of
    INDEPENDENT source origins (``corroboration.py``) — ten mirrors of one page count
    once, so mirror-stuffing cannot raise the score;
  - an asserted-but-uncorroborated value is counted as NOISE and LOWERS the score, so
    "self-add data" cannot become a hallucination reward;
  - the held-out guard rejects benchmark-gaming.

Everything here is pure and offline (no LLM, no DB) so P1/P2 run as unit tests. The real
pi/feynman proposer and the Postgres corroboration ledger (002_selfimprove.sql) drop in
behind the same ``Proposer`` seam without changing the gate.
"""
from __future__ import annotations

from .corroboration import confidence, independent_origins, origin_key
from .gate import Datum, Decision, gate, round_score, score_entity
from .loop import Candidate, RoundResult, run_loop

__all__ = [
    "origin_key", "independent_origins", "confidence",
    "Datum", "Decision", "score_entity", "round_score", "gate",
    "Candidate", "RoundResult", "run_loop",
]
