"""Matcher port (D10, R12) + the deterministic rule-filter (R2).

The `Matcher` protocol makes ranking pluggable: v1 is `LlmJudgeMatcher` (pi ranks +
explains the filtered handful, no embeddings); `EmbeddingMatcher` / `GraphRagMatcher`
drop in later with no saga change (spec §12).

    async def rank(startup, candidates, ctx) -> list[ScoredMatch]

The rule-filter is a cheap deterministic pre-cut that runs in the spine (never calls
an LLM). Per R2 it is PERMISSIVE — it must never collapse to zero:
  - sector overlap is the only hard gate, and only when BOTH sides carry sectors;
    a missing sector signal passes through flagged `low_confidence_filter`.
  - purpose (`looking_for`) NEVER hard-drops a partner — a purpose mismatch only sets
    `low_confidence_filter`, leaving the LLM judge to down-rank it.
Sector tags are matched on a BILINGUAL normalization table so `enterprise_ai` and `ai`,
`clean_energy` and `cleantech`, `nông nghiệp` and `agritech` intersect.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol, runtime_checkable

from spine.ids import slugify

PARTNER_TYPES = ("investor", "corporation", "university", "research_institution")

# looking_for purpose -> partner types it implies (spec §6 rule-filter / dealflow §1).
PURPOSE_TYPES: dict[str, set[str]] = {
    "funding": {"investor"},
    "corporate_pilot": {"corporation"},
    "strategic_partnership": {"corporation"},
    "market_access": {"corporation"},
    "rd_collaboration": {"university", "research_institution"},
    "talent": {"university", "research_institution"},
}

# Bilingual sector normalization (R2). raw tag -> canonical English tag. Aligned with the
# extract-stage prompt so startup + partner tags land in the same space.
_SECTOR_MAP: dict[str, str] = {
    "enterprise_ai": "ai", "ai_agents": "ai", "automation": "ai", "machine_learning": "ai",
    "ml": "ai", "genai": "ai", "llm": "ai", "ai_ml": "ai", "artificial_intelligence": "ai",
    "tri_tue_nhan_tao": "ai",
    "clean_energy": "cleantech", "cleantech": "cleantech", "renewable_energy": "cleantech",
    "renewables": "cleantech", "thermal_energy_storage": "cleantech",
    "nang_luong_sach": "cleantech",
    "energy": "energy", "smart_grid": "energy", "nang_luong": "energy",
    "agritech": "agritech", "agtech": "agritech", "agriculture": "agritech",
    "smart_agriculture": "agritech", "foodtech": "agritech", "food_tech": "agritech",
    "nong_nghiep": "agritech",
    "healthcare": "healthtech", "biotech": "healthtech", "healthtech": "healthtech",
    "medtech": "healthtech", "life_sciences": "healthtech", "health": "healthtech",
    "y_te": "healthtech",
    "supply_chain": "supply_chain", "logistics": "supply_chain",
    "chuoi_cung_ung": "supply_chain",
    "digital_transformation": "digital_transformation",
    "digital_infrastructure": "digital_transformation",
    "digitalization": "digital_transformation", "dx": "digital_transformation",
    "esg": "sustainability", "sustainability": "sustainability",
    "circular_economy": "sustainability",
}


def _canon(tag: str) -> str:
    # slugify strips Vietnamese diacritics (đ + NFKD) so "nông nghiệp" -> "nong-nghiep".
    t = slugify(str(tag)).replace("-", "_")
    return _SECTOR_MAP.get(t, t)


def normalize_sectors(tags) -> set[str]:
    """Canonicalize a list of raw sector/domain tags to the shared matching space."""
    if not tags:
        return set()
    if isinstance(tags, str):
        tags = [tags]
    return {c for c in (_canon(t) for t in tags) if c}


def _partner_sectors(entity: dict) -> set[str]:
    """Union of a partner's normalized sectors and its seed innovation/research hints."""
    prof = entity.get("profile") or {}
    tags = list((prof.get("normalized") or {}).get("sectors") or [])
    seed = prof.get("seed") or {}
    for key in ("sectors", "innovation_areas", "research_domains"):
        tags += seed.get(key) or []
    return normalize_sectors(tags)


@dataclass(slots=True)
class ScoredMatch:
    partner_id: str
    partner_name: str
    partner_type: str
    composite: float                 # 0-100 fit score
    rationale_en: str
    rationale_vi: str
    semantic: float | None = None    # 0-1 (optional, LLM self-report)
    sector_overlap: float | None = None


@runtime_checkable
class Matcher(Protocol):
    """Pluggable ranking port (R12). Ranks a pre-filtered candidate handful for one
    startup and returns explained ScoredMatch rows, best first."""

    async def rank(self, startup: dict, candidates: list[dict],
                   ctx: dict) -> list[ScoredMatch]: ...


def rule_filter(startup: dict, partners: list[dict]) -> list[dict]:
    """Deterministic permissive pre-cut (R2). Returns candidate dicts, never empty
    unless every partner has a disjoint non-empty sector set.

    startup: {"sectors": [...], "looking_for": [...], "stage": str|None}
    partner entity dicts must carry id, name, type, profile.
    """
    s_sectors = normalize_sectors(startup.get("sectors"))
    looking_for = [str(x) for x in (startup.get("looking_for") or [])]
    implied: set[str] = set()
    for p in looking_for:
        implied |= PURPOSE_TYPES.get(p, set())

    out: list[dict] = []
    for partner in partners:
        p_sectors = _partner_sectors(partner)
        # --- sector gate: the ONLY hard drop, and only when both sides have data ---
        if s_sectors and p_sectors:
            overlap = s_sectors & p_sectors
            if not overlap:
                continue
            sector_lc = False
        else:
            overlap = set()
            sector_lc = True  # missing signal -> pass through, low confidence
        # --- purpose: never drops; a mismatch only flags low confidence ---
        if not implied:
            purpose_lc = True
        else:
            purpose_lc = partner["type"] not in implied
        out.append({
            "partner_id": partner["id"],
            "partner_name": partner["name"],
            "partner_type": partner["type"],
            "sector_overlap": sorted(overlap),
            "purpose_match": bool(implied) and not purpose_lc,
            "low_confidence_filter": sector_lc or purpose_lc,
        })
    return out
