# Self-Improvement Loop — Design & Verification Spec

- **Date:** 2026-07-19
- **Problem:** #135 Deal-flow Matchmaker (VAIC 2026, sponsor NIC)
- **Status:** Mechanism proven offline (P1 + P2, 9/9 tests green). Live proposer + Postgres ledger NOT yet wired.
- **Depends on:** [2026-07-18 Agent Data Platform Design](2026-07-18-agent-data-platform-design.md) (spine/agent split, provenance discipline, saga model)

---

## 1. Summary — the big change

The platform gains a **self-improvement layer**: a loop that lets the system *evaluate whether its own data/matching can be better and promote a change only when it provably is* — with no human in the loop. This is the first step toward the "self-evolving agents" ambition (agents that run, watch logs, detect data problems, self-add data, self-version, self-evaluate).

The change is deliberately scoped to the **one link that makes the ambition non-fake**: a **deterministic promotion gate**. Everything else (continuous daemon, auto-enrichment, profile storage) is plumbing the platform already has; the risk was always a loop *drifting without a ground truth to check against*. This spec pins that ground truth down and proves the gate can't be fooled.

**Falsifiable claim (now verified in miniature, on `funding_stage`):**
> The system can propose a new value-set/version, score it against a frozen benchmark, and promote it **only** when it beats the incumbent, does not regress a held-out slice, and every asserted datum is independently corroborated — raising the score over rounds without a human.

---

## 2. The reasoning that shaped it (why the design is this shape)

The design is the residue of one recurring danger, argued through four layers:

1. **"Self-evolving" is a vibe unless "better" is measurable.** The whole idea reduces to: *can a change be accepted only if it provably beats the incumbent on a frozen, held-out benchmark, with no human?* If you can't measure better, you have an agent that *feels* like it's improving while silently regressing.

2. **The ground truth is data quality — but that word hides three different problems.** Correctness (truth vs. source) and completeness/noise are largely *checkable*; "good insight to founders/investors" is subjective (weak, judge-only); "can it adapt to new query criteria" is a *capability* axis, not a quality metric. They must be verified separately or they collapse into one gameable score.

3. **Correctness is only verifiable by cross-check across INDEPENDENT sources.** A single source can be stale, biased, or a mirror. Ten Crunchbase mirrors are one confirmation echoed ten times, not ten confirmations. So correctness is *independence-weighted corroboration*, yielding a **confidence**, not a boolean. Disagreement is signal (surface conflicts), not failure.

4. **The through-line across every layer** — promotion, judging, correctness — **is the same failure mode: a system confirming itself with correlated evidence.** The entire safeguard is enforcing *genuine independence* between the thing being checked and the thing doing the checking:
   - the **agent being scored never computes its own score** (the gate is pure spine logic);
   - **confidence counts distinct source origins**, so mirror-stuffing can't raise it;
   - an asserted-but-uncorroborated value is **noise that lowers the score**, so "self-add data" can't become a hallucination reward;
   - the **held-out slice** rejects benchmark-gaming.

### The two-set trick that avoids circularity

If "correctness" *is* corroboration and the loop's job *is* to corroborate, scoring looks circular. It's broken by separating:

- **Gold set** — built once, expensively, offline (generous cross-check + human spot-check on ~10). Frozen. The target.
- **Production output** — what the cheap, cost-capped pipeline produces at run time. The score is how well production hits the frozen gold. Not circular: gold is a one-time ceiling the loop tries to reach.

---

## 3. The metric (what "better" means)

```
round_score = mean( correct * confidence )  -  lambda * noise_rate

  correct     = 1 if produced value == frozen gold value, else 0
  confidence  = min(1, (indep_origins - 1) / (K - 1))   # n=1 -> 0.0, n=2 -> 0.5, n>=K -> 1.0
  noise_rate  = fraction of gold entities with a value ASSERTED on < 2 independent origins
  K           = independent origins required for full confidence (default 3)
  lambda      = noise penalty weight (default 0.5)
```

This is the whole anti-gaming engine in one line:

- guessing the gold value can't win — confidence stays 0;
- mirror-stuffing can't win — independence stays 1 → confidence 0 **and** a noise penalty;
- inventing data actively **lowers** the score;
- a *missing* value simply scores 0 (not an assertion → not noise) — the loop is rewarded for **grounding**, never for filling.

`indep_origins` counts distinct **origin keys** (registered domain / upstream of a URL), not URLs — so syndication collapses.

---

## 4. The gate (P1) and the loop (P2)

**Gate** — a pure function in the spine; the agent that produced a candidate can never influence its verdict:

```
promote(candidate) iff
    round_score(candidate, bench)     >  incumbent_bench_score + eps      # strict improvement
AND round_score(candidate, held_out)  >= incumbent_held_out_score - eps   # no regression
# grounding is enforced implicitly: zero-source / mirror-only data scores 0 + noise penalty
```

**Loop** — `observe -> propose -> gate`, N rounds, unattended. Each round a `Proposer` returns a full candidate value-set ("version"); the incumbent advances only on PROMOTE, so a rejected round leaves the score flat. The `Proposer` signature is the seam where the live pi/feynman agent drops in without changing the gate.

---

## 5. What was built (this change)

Additive only — no existing module touched.

| Path | Role |
|---|---|
| `apps/matchmaker/selfimprove/corroboration.py` | `origin_key` (mirror → origin), `independent_origins`, `confidence` |
| `apps/matchmaker/selfimprove/gate.py` | `Datum`, `round_score`, pure `gate()` |
| `apps/matchmaker/selfimprove/loop.py` | `run_loop` over the `Proposer` seam |
| `apps/matchmaker/migrations/002_selfimprove.sql` | `datum` / `source` / `version` / `eval_run` ledger — **schema only, not yet wired** |
| `tests/test_selfimprove_gate.py` | **P1** — 5 adversarial gate cases + origin tests |
| `tests/test_selfimprove_loop.py` | **P2** — curve climbs + hallucination round rejected |

The `datum`/`source` ledger normalizes the `{value, source_url, confidence}` convention that `entities.profile` already documents into a real multi-source ledger (one datum, many independent origins). `version`/`eval_run` are the self-versioning audit and the P2 curve source.

---

## 6. Verification results

**P1 — the gate rejects garbage** (deterministic, no LLM/DB). All must resolve as shown:

| Case | Input | Result |
|---|---|---|
| G1 | Worse matcher (flips stages) | REJECT — no improvement |
| G2 | Hallucinated datum, zero sources | REJECT — noise drags score |
| G3 | Mirror-stuffed (10 URLs, 1 origin) | REJECT — independence stays 1 |
| G4 | Improves bench, regresses held-out | REJECT — held-out guard |
| G5 | Correct **and** ≥2 independent origins | **PROMOTE** (control) |

**P2 — the loop climbs unattended**, and the gate catches a mid-run hallucination:

```
round 0  promote  score=0.250
round 1  promote  score=0.500
round 2  reject   no improvement   score=0.500   <- zero-source hallucination caught; curve flat
round 3  promote  score=0.750
round 4  promote  score=1.000
```

**Status: 9/9 tests green.** `uv run pytest tests/test_selfimprove_gate.py tests/test_selfimprove_loop.py`

---

## 7. Honest scope — proven vs. next

- **Proven, deterministically:** the *gate* is un-gameable — mirror-stuffing, zero-source hallucination, worse matcher, and benchmark-gaming all reject; only correct-**and**-independently-grounded improvements promote. Needs no LLM to trust.
- **Simulated, not yet live:** the P2 proposer is a deterministic stand-in for the pi/feynman agent. It proves the *mechanism*, not that a real agent can find independent sources. Drops in behind the same `Proposer` signature.

### Not yet done (deferred, by design)

- Live proposer wired into a supervisor saga (agent reads `eval_run` breakdown → fetches + corroborates weakest entities → writes candidate `datum`/`source` → spine runs this `gate()` against a frozen slice of the dump).
- Applying `002_selfimprove.sql` and building the gold set from `dump_dealflow_20260719.sql`.
- **Adaptability test (the real "evolving"):** held-out *new* query criteria the system was never built for — a separate pass/fail capability test, not a quality score.
- Judge-based signals (weak, secondary) and the human spot-check on ~10 cases.

---

## 8. Decisions (locked for this layer)

| # | Decision | Choice |
|---|---|---|
| S1 | Ground truth | Independence-weighted **corroboration** (confidence), not judge opinion or single-source |
| S2 | Independence unit | Distinct **origin key** (registered domain / upstream), not URL — mirrors collapse |
| S3 | Un-gameability | Scored party never computes its own score — **gate is pure spine logic** |
| S4 | Ungrounded data | < 2 independent origins = **noise**, penalized — self-add can't reward hallucination |
| S5 | Anti-gaming guard | **Held-out slice**; promote requires no regression on it |
| S6 | First field | `funding_stage` (ordinal, cheap, match-driving) — smallest real proof |
| S7 | Prove offline first | P1/P2 as pure unit tests before any LLM/DB spend |

---

## 9. Related

- Pre-existing broken test flagged during this work (unrelated): `tests/test_enrichment_gate.py` imports `spine.sagas`, moved into `spindle`/`apps` by the Phase-4/5 refactor (`0855323`, `abb7197`). Needs a separate `[fix]`.
