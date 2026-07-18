"""LlmJudgeMatcher — v1 Matcher (D10, R12).

Ranks + explains a pre-filtered candidate handful with a single pi call (dealflow-match
§3), no embeddings. It does not spawn processes itself: the supervisor injects a
`runner` — an async callable `(prompt) -> RpcResult` that runs one pi turn and records
usage — so the pi-spawn/telemetry logic stays in one place. rank() builds the prompt,
parses the R3 rank.json terminal block, and maps it to ScoredMatch rows.
"""
from __future__ import annotations

import json
from typing import Awaitable, Callable

from . import ScoredMatch, normalize_sectors

RpcRunner = Callable[[str], Awaitable[object]]


def _startup_view(startup: dict) -> dict:
    prof = startup.get("profile") or {}
    norm = prof.get("normalized") or {}
    return {
        "name": startup.get("name"),
        "sectors": sorted(normalize_sectors(norm.get("sectors"))),
        "stage": norm.get("stage"),
        "looking_for": norm.get("looking_for") or ["funding"],
        "description_en": norm.get("description_en"),
        "description_vi": norm.get("description_vi"),
    }


def _candidate_view(entity: dict) -> dict:
    prof = entity.get("profile") or {}
    norm = prof.get("normalized") or {}
    seed = prof.get("seed") or {}
    desc = norm.get("description_en") or seed.get("note")
    tags = list(norm.get("sectors") or []) or (
        seed.get("innovation_areas") or seed.get("research_domains") or seed.get("sectors") or []
    )
    return {
        "partner_id": entity.get("id"),
        "name": entity.get("name"),
        "type": entity.get("type"),
        "sectors": sorted(normalize_sectors(tags)),
        "description": desc,
    }


def build_rank_prompt(startup_view: dict, candidate_views: list[dict], *,
                      top_k: int, retry: bool = False) -> str:
    reminder = ("\n\nIMPORTANT: your previous reply was invalid. Respond with ONLY a single "
                "fenced ```json block and nothing else.") if retry else ""
    return f"""You are a match analyst at Vietnam's National Innovation Center (NIC).

Rank how well each PARTNER fits this STARTUP for a deal-flow introduction, then explain
the top {top_k}. Partners span four types — investor (funding), corporation (pilots /
strategic partnership), university & research_institution (R&D collaboration). Judge fit
on sector/technology alignment, the startup's `looking_for`, and stage/geography signals.

STARTUP
{json.dumps(startup_view, ensure_ascii=False, indent=2)}

PARTNER CANDIDATES (already coarse-filtered on sector overlap)
{json.dumps(candidate_views, ensure_ascii=False, indent=2)}

For each partner produce:
- composite: integer 0-100 fit score (higher = stronger match)
- semantic: 0.0-1.0 your semantic-similarity estimate (or null)
- sector_overlap: 0.0-1.0 fraction of the startup's sectors the partner covers (or null)
- rationale_en: 2-3 sentences — what specifically aligns, the concrete value the
  partnership could create, and one honest risk/concern. Under 80 words.
- rationale_vi: the same rationale in natural Vietnamese.

Ground every claim in the data above — do NOT invent facts, metrics, or history.

OUTPUT (R3 contract): reply with ONLY a single fenced ```json block:
{{"matches": [{{"partner_id": "...", "composite": 87, "semantic": 0.84,
  "sector_overlap": 0.9, "rationale_en": "...", "rationale_vi": "..."}}]}}
Include one object per partner above, sorted by composite descending. No prose.{reminder}"""


class LlmJudgeMatcher:
    def __init__(self, runner: RpcRunner, *, top_k: int = 5):
        self._runner = runner
        self._top_k = top_k

    async def rank(self, startup: dict, candidates: list[dict],
                   ctx: dict) -> list[ScoredMatch]:
        if not candidates:
            return []
        sv = _startup_view(startup)
        cvs = [_candidate_view(c) for c in candidates]
        by_id = {c.get("id"): c for c in candidates}
        prompt = build_rank_prompt(sv, cvs, top_k=self._top_k,
                                   retry=bool(ctx.get("retry")))
        result = await self._runner(prompt)
        if not getattr(result, "success", False):
            return []
        data = getattr(result, "data", None)
        if not isinstance(data, dict) or not isinstance(data.get("matches"), list):
            return []

        scored: list[ScoredMatch] = []
        for m in data["matches"]:
            pid = m.get("partner_id")
            ent = by_id.get(pid)
            if ent is None or not m.get("rationale_en"):
                continue  # ignore hallucinated / out-of-set partner ids
            try:
                composite = float(m.get("composite"))
            except (TypeError, ValueError):
                continue
            scored.append(ScoredMatch(
                partner_id=pid,
                partner_name=ent.get("name") or pid,
                partner_type=ent.get("type") or "",
                composite=max(0.0, min(100.0, composite)),
                rationale_en=m.get("rationale_en") or "",
                rationale_vi=m.get("rationale_vi") or "",
                semantic=_as_float(m.get("semantic")),
                sector_overlap=_as_float(m.get("sector_overlap")),
            ))
        scored.sort(key=lambda s: s.composite, reverse=True)
        return scored


def _as_float(v) -> float | None:
    try:
        return None if v is None else float(v)
    except (TypeError, ValueError):
        return None
