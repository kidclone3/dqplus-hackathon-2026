"""Embedding + attribute-scoring unit tests. Pure, no DB.

Covers the deterministic fallback path (spec §12, OPENAI_API_KEY optional):
  - spine.embedding.entity_text: a normalized profile becomes the text we embed.
  - spine.embedding.embed_text: with OPENAI_API_KEY unset it falls back to a
    deterministic, L2-normalized vector of length EMBEDDING_DIM (no network).
  - spine.matcher.embedding_matcher.attribute_score: the pure structured-signal
    helper — sector overlap raises the score and emits a reason; disjoint sectors
    score lower; stage and geo matches each add their own reason.

These modules are built in parallel; the assertions target the documented API only.
"""
import asyncio
import math

import pytest

from apps.matchmaker.embedding import EMBEDDING_DIM, embed_text, entity_text
from apps.matchmaker.matcher.embedding_matcher import attribute_score


# ── helpers ────────────────────────────────────────────────────────

def _unpack(result):
    """attribute_score returns a score + its reasons. Tolerate the reasonable
    shapes (tuple, dict, or object) since the module is built in parallel."""
    if isinstance(result, (tuple, list)):
        score, reasons = result[0], result[1]
    elif isinstance(result, dict):
        score = result.get("score")
        reasons = result.get("reasons") or result.get("reason") or []
    else:
        score = getattr(result, "score")
        reasons = getattr(result, "reasons", [])
    return float(score), list(reasons)


def _reason_text(reasons) -> str:
    return " ".join(str(r) for r in reasons).lower()


def _norm(vec) -> float:
    return math.sqrt(sum(v * v for v in vec))


# ── entity_text ────────────────────────────────────────────────────

def test_entity_text_builds_text_from_normalized_profile():
    profile = {
        "sectors": ["ai", "agritech"],
        "looking_for": ["funding"],
        "stage": "seed",
        "description_en": "AI-driven soil sensors for smallholder farms.",
        "description_vi": "Cảm biến đất dùng AI cho nông hộ nhỏ.",
    }
    text = entity_text(profile)
    assert isinstance(text, str)
    assert text.strip()                          # non-empty
    low = text.lower()
    assert "agritech" in low                     # sectors folded in
    assert "seed" in low                         # stage folded in
    assert "soil sensors" in low                 # description carried through


# ── embed_text fallback ────────────────────────────────────────────

def test_embed_text_fallback_shape_and_normalized(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)   # force deterministic path
    vec = asyncio.run(embed_text("AI-driven soil sensors for smallholder farms"))
    assert isinstance(vec, list)
    assert len(vec) == EMBEDDING_DIM
    assert all(isinstance(v, float) for v in vec)
    assert _norm(vec) == pytest.approx(1.0, abs=1e-6)     # L2-normalized


def test_embed_text_fallback_is_deterministic(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    a = asyncio.run(embed_text("Series A fintech, Vietnam"))
    b = asyncio.run(embed_text("Series A fintech, Vietnam"))
    assert a == b                                          # identical across calls
    # distinct inputs must not collapse to the same vector
    assert asyncio.run(embed_text("cleantech, Singapore")) != a


# ── attribute_score ────────────────────────────────────────────────

def test_sector_overlap_raises_score_and_emits_reason(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    query = {"sectors": ["ai"], "stage": "seed", "geo": "Vietnam", "country": "Vietnam"}
    overlap = {"sectors": ["ai"], "stage": "seed", "geo": "Vietnam", "country": "Vietnam"}
    disjoint = {"sectors": ["agritech"], "stage": "seed", "geo": "Vietnam", "country": "Vietnam"}

    hi_score, hi_reasons = _unpack(attribute_score(query, overlap))
    lo_score, lo_reasons = _unpack(attribute_score(query, disjoint))

    assert hi_score > lo_score                             # overlap wins
    assert "sector" in _reason_text(hi_reasons)            # overlap emits a reason
    assert "sector" not in _reason_text(lo_reasons)        # disjoint doesn't claim overlap


def test_stage_match_adds_its_reason(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    query = {"sectors": ["ai"], "stage": "seed"}
    same_stage = {"sectors": ["ai"], "stage": "seed"}
    diff_stage = {"sectors": ["ai"], "stage": "series_b"}

    match_score, match_reasons = _unpack(attribute_score(query, same_stage))
    miss_score, _ = _unpack(attribute_score(query, diff_stage))

    assert "stage" in _reason_text(match_reasons)
    assert match_score >= miss_score


def test_geo_match_adds_its_reason(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    query = {"sectors": ["ai"], "geo": "Vietnam", "country": "Vietnam"}
    same_geo = {"sectors": ["ai"], "geo": "Vietnam", "country": "Vietnam"}
    diff_geo = {"sectors": ["ai"], "geo": "Singapore", "country": "Singapore"}

    match_score, match_reasons = _unpack(attribute_score(query, same_geo))
    miss_score, _ = _unpack(attribute_score(query, diff_geo))

    text = _reason_text(match_reasons)
    assert "geo" in text or "vietnam" in text or "location" in text
    assert match_score >= miss_score
