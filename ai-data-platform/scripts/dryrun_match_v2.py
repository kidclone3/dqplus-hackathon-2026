"""Dry-run the match stage against the FPT-hosted model, writing to matches_v2.

Reuses the REAL matcher path — deterministic rule_filter (spine/matcher) then the
LlmJudgeMatcher pi call — so results are comparable to the live `matches` table.
Nothing in `matches` is touched; new rows land in `matches_v2` (created if absent).

Run:
    export FPT_API_KEY='...'
    docker compose up -d postgres
    uv run python scripts/dryrun_match_v2.py            # all startups with matches
    uv run python scripts/dryrun_match_v2.py --limit 3  # smoke a few
"""
from __future__ import annotations

import argparse
import asyncio
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))  # run directly

from spine import config, pools
from apps.matchmaker.matcher import rule_filter
from apps.matchmaker.matcher.llm_judge import LlmJudgeMatcher
from apps.matchmaker.store import MatchmakerStore as Store
from spine.transport import LocalProcessLauncher

MODEL = os.environ.get("DRYRUN_MODEL", "fptcloud/DeepSeek-V4-Flash")

DDL = """
CREATE TABLE IF NOT EXISTS matches_v2 (
  id bigserial PRIMARY KEY,
  startup_id text,
  partner_id text,
  composite real,
  semantic real,
  sector_overlap real,
  rationale_en text,
  rationale_vi text,
  trace_id text,
  status text NOT NULL DEFAULT 'ranked',
  model text,
  created_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE (startup_id, partner_id)
);
"""

UPSERT = """
INSERT INTO matches_v2 (startup_id, partner_id, composite, semantic, sector_overlap,
                        rationale_en, rationale_vi, trace_id, status, model)
VALUES ($1,$2,$3,$4,$5,$6,$7,$8,'ranked',$9)
ON CONFLICT (startup_id, partner_id) DO UPDATE
  SET composite=EXCLUDED.composite, semantic=EXCLUDED.semantic,
      sector_overlap=EXCLUDED.sector_overlap, rationale_en=EXCLUDED.rationale_en,
      rationale_vi=EXCLUDED.rationale_vi, trace_id=EXCLUDED.trace_id,
      model=EXCLUDED.model, created_at=now();
"""


def make_runner(launcher: LocalProcessLauncher, spec, tag: str):
    """One fresh pi process per rank() call (R7 hygiene), mirroring _run_worker."""
    async def runner(prompt: str):
        ch = await launcher.spawn(spec, f"dryrun-{tag}")
        try:
            return await ch.prompt(prompt, timeout=config.AGENT_TIMEOUT)
        finally:
            await ch.close()
    return runner


async def rank_one(store: Store, launcher: LocalProcessLauncher, spec,
                   startup_id: str, partners: list[dict], sem: asyncio.Semaphore) -> dict:
    startup = await store.get_entity(startup_id)
    if not startup:
        return {"startup_id": startup_id, "status": "no_entity", "n": 0}
    norm = (startup["profile"].get("normalized") or {})
    startup_view = {"sectors": norm.get("sectors"),
                    "looking_for": norm.get("looking_for") or ["funding"],
                    "stage": norm.get("stage")}
    cands = rule_filter(startup_view, partners)
    cands.sort(key=lambda c: (c["low_confidence_filter"], not c["purpose_match"]))
    cands = cands[: config.MATCH_MAX_CANDIDATES]
    if not cands:
        return {"startup_id": startup_id, "status": "no_candidates", "n": 0}

    by_id = {p["id"]: p for p in partners}
    cand_entities = [by_id[c["partner_id"]] for c in cands if c["partner_id"] in by_id]

    async with sem:
        runner = make_runner(launcher, spec, tag=startup_id.split(":")[-1])
        matcher = LlmJudgeMatcher(runner, top_k=config.MATCH_TOP_K)
        scored = await matcher.rank(startup, cand_entities, ctx={})

    if not scored:
        return {"startup_id": startup_id, "status": "match_empty", "n": 0}

    top = scored[: config.MATCH_TOP_K]
    for m in top:
        await store.pool.execute(
            UPSERT, startup_id, m.partner_id, m.composite, m.semantic,
            m.sector_overlap, m.rationale_en, m.rationale_vi, "fpt-v2-dryrun", MODEL,
        )
    return {"startup_id": startup_id, "status": "ok", "n": len(top),
            "top": [(m.partner_id, round(m.composite, 1)) for m in top]}


async def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=0, help="cap number of startups (0=all)")
    args = ap.parse_args()

    if not os.environ.get("FPT_API_KEY"):
        raise SystemExit("FPT_API_KEY not set — export it before running.")

    store = await Store.connect()
    await store.pool.execute(DDL)

    rows = await store.pool.fetch("SELECT DISTINCT startup_id FROM matches ORDER BY startup_id")
    startup_ids = [r["startup_id"] for r in rows]
    if args.limit:
        startup_ids = startup_ids[: args.limit]

    specs = pools.load_specs()
    spec = pools.specs_by_stage(specs)["match"]
    spec.model = MODEL
    spec.skill = os.path.abspath(spec.skill)  # resolvable from the scratch cwd
    scratch = os.path.join(os.getcwd(), ".agent-scratch")
    os.makedirs(scratch, exist_ok=True)
    launcher = LocalProcessLauncher(cwd=scratch)

    partners = await store.list_ready_partners()
    sem = asyncio.Semaphore(config.MAX_CONCURRENCY)
    print(f"dry-run: {len(startup_ids)} startups | model={MODEL} | "
          f"{len(partners)} ready partners | concurrency={config.MAX_CONCURRENCY}")

    tasks = [rank_one(store, launcher, spec, sid, partners, sem) for sid in startup_ids]
    done = 0
    for coro in asyncio.as_completed(tasks):
        res = await coro
        done += 1
        print(f"[{done}/{len(startup_ids)}] {res['startup_id']:40} {res['status']:14} "
              f"n={res['n']} {res.get('top', '')}")

    await store.close()


if __name__ == "__main__":
    asyncio.run(main())
