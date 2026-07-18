"""EmbeddingMatcher — pgvector RAG match (spec §12 drop-in for the Matcher port).

A requester profile is embedded once (embedding.embed_text) and KNN-searched against the
`entities.embedding` corpus, then re-scored with a pure attribute score. The composite
mirrors the matching-engine: ``vector_weight * vscore + attr_weight * attr`` (0.7 / 0.3).

`attribute_score` is a standalone PURE function (no I/O) so the rules are unit-testable
without a DB. It mirrors matching-engine/scoring.py weights — sector Jaccard 0.4, stage
0.3, geo/region 0.2, check-size fit 0.1 / 0.05 — over the entity `profile.normalized`
shape, and each firing rule appends a human-readable reason.

asyncpg has no vector adapter, so the query embedding is passed as a pgvector literal
string and cast `$1::vector` in SQL.
"""
from __future__ import annotations

import asyncio
import json
import os
import urllib.request

from . import normalize_sectors
from ..embedding import embed_text, entity_text

OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY") or ""
OPENAI_BASE_URL = os.environ.get("OPENAI_BASE_URL") or "https://mkp-api.fptcloud.com"
OPENAI_CHAT_MODEL = os.environ.get("OPENAI_CHAT_MODEL") or "gemma-4-31B-it"


# ── Pure attribute scoring (no I/O, unit-testable) ─────────────────────────────────
def attribute_score(query_norm: dict, cand_norm: dict) -> tuple[float, list[str]]:
    """Score a candidate's `normalized` profile against the requester's. Returns
    (score in [0, 1], reasons). Mirrors matching-engine/scoring.py weights."""
    query_norm = query_norm or {}
    cand_norm = cand_norm or {}
    reasons: list[str] = []
    score = 0.0

    # sector overlap (Jaccard, bilingual-normalized) — weight 0.4
    q_sectors = normalize_sectors(query_norm.get("sectors"))
    c_sectors = normalize_sectors(cand_norm.get("sectors"))
    if q_sectors and c_sectors:
        overlap = q_sectors & c_sectors
        if overlap:
            score += 0.4 * (len(overlap) / len(q_sectors | c_sectors))
            reasons.append(f"sector overlap: {', '.join(sorted(overlap))}")

    # stage match — weight 0.3
    q_stage = str(query_norm.get("stage") or "").lower().strip()
    c_stages = _lower(_as_list(cand_norm.get("stages") or cand_norm.get("stage")))
    if q_stage and q_stage in c_stages:
        score += 0.3
        reasons.append(f"stage match: {q_stage}")

    # geo / region match — weight 0.2
    q_regions = set(_lower(_regions(query_norm)))
    c_geos = set(_lower(_regions(cand_norm)))
    if "global" in c_geos and q_regions:
        score += 0.2
        reasons.append("partner operates globally")
    else:
        geo_overlap = q_regions & c_geos
        if geo_overlap:
            score += 0.2
            reasons.append(f"geography match: {', '.join(sorted(geo_overlap))}")

    # check-size fit — weight 0.1 (both bounds) / 0.05 (one bound)
    ask = _num(query_norm.get("funding_ask_usd") or query_norm.get("check_size_usd"))
    min_check = _num(cand_norm.get("check_size_min_usd"))
    max_check = _num(cand_norm.get("check_size_max_usd"))
    if ask is not None and (min_check is not None or max_check is not None):
        above_min = min_check is None or ask >= min_check
        below_max = max_check is None or ask <= max_check
        if above_min and below_max:
            score += 0.1 if (min_check is not None and max_check is not None) else 0.05
            reasons.append("check size fits funding ask")

    return min(score, 1.0), reasons


# ── pgvector RAG match ─────────────────────────────────────────────────────────────
async def match(pool, *, query_profile: dict | None = None, query_text: str | None = None,
                query_norm: dict | None = None, target_types: list[str], limit: int,
                filters: dict | None = None, rerank: bool = False,
                vector_weight: float = 0.7, attr_weight: float = 0.3) -> dict:
    # query_text/query_norm let a caller supply a pre-built text + normalized dict (e.g. a
    # gateway user's extracted_profiles row); otherwise both are derived from query_profile.
    if query_norm is None:
        query_norm = _normalized(query_profile or {})
    source_text = query_text if query_text is not None else entity_text(query_profile or {})
    vec = await embed_text(source_text)
    vec_literal = "[" + ",".join(str(x) for x in vec) + "]"

    conditions = ["type = ANY($2)", "embedding IS NOT NULL"]
    params: list = [vec_literal, target_types]
    for key, value in (filters or {}).items():
        params.append(json.dumps({key: value}))
        conditions.append(f"profile->'normalized' @> ${len(params)}::jsonb")

    candidate_pool = max(50, limit)
    query = f"""
        SELECT id, type, name, profile, 1 - (embedding <=> $1::vector) AS vscore
        FROM entities
        WHERE {' AND '.join(conditions)}
        ORDER BY embedding <=> $1::vector
        LIMIT {candidate_pool}
    """
    rows = await pool.fetch(query, *params)

    matches = []
    for r in rows:
        profile = r["profile"]
        if isinstance(profile, str):
            profile = json.loads(profile) if profile else {}
        vscore = float(r["vscore"])
        attr, reasons = attribute_score(query_norm, (profile or {}).get("normalized") or {})
        composite = vector_weight * vscore + attr_weight * attr
        matches.append({
            "id": r["id"],
            "name": r["name"],
            "type": r["type"],
            "score": round(composite, 4),
            "vectorScore": round(vscore, 4),
            "attributeScore": round(attr, 4),
            "reasons": reasons,
            "profile": profile or {},
        })

    matches.sort(key=lambda m: m["score"], reverse=True)
    matches = matches[:limit]

    if rerank and matches:
        await _rerank(query_norm, matches)

    return {"matches": matches}


# ── Optional LLM rerank (cited rationale) ──────────────────────────────────────────
async def _rerank(query_norm: dict, matches: list[dict]) -> None:
    """Attach cited rationale_en/rationale_vi to `matches` in place via one FPT chat
    call. On ANY failure (no key, network, bad JSON) the rationales are omitted silently."""
    if not OPENAI_API_KEY:
        return
    try:
        data = await asyncio.to_thread(_chat_rerank, query_norm, matches)
        by_id = {m["id"]: m for m in matches}
        for item in data.get("items") or []:
            m = by_id.get(item.get("id"))
            if m is None:
                continue
            if item.get("rationale_en"):
                m["rationale_en"] = str(item["rationale_en"])
            if item.get("rationale_vi"):
                m["rationale_vi"] = str(item["rationale_vi"])
    except Exception:
        pass


def _chat_rerank(query_norm: dict, matches: list[dict]) -> dict:
    requester = {
        "sectors": sorted(normalize_sectors(query_norm.get("sectors"))),
        "stage": query_norm.get("stage"),
        "looking_for": query_norm.get("looking_for"),
        "description_en": query_norm.get("description_en"),
    }
    candidates = [
        {
            "id": m["id"],
            "name": m["name"],
            "type": m["type"],
            "reasons": m["reasons"],
            "normalized": (m["profile"] or {}).get("normalized") or {},
        }
        for m in matches
    ]
    prompt = (
        "Explain why each PARTNER fits this REQUESTER for a Vietnamese innovation "
        "introduction. Ground every claim ONLY in the data below — invent nothing.\n\n"
        f"REQUESTER\n{json.dumps(requester, ensure_ascii=False)}\n\n"
        f"PARTNERS\n{json.dumps(candidates, ensure_ascii=False)}\n\n"
        "Reply with ONLY valid JSON: {\"items\": [{\"id\": \"...\", \"rationale_en\": "
        "\"1-2 sentences on the concrete fit\", \"rationale_vi\": \"same in Vietnamese\"}]}. "
        "One object per partner above."
    )
    payload = json.dumps({
        "model": OPENAI_CHAT_MODEL,
        "messages": [
            {"role": "system", "content": "You are a match analyst. Reply with valid JSON only."},
            {"role": "user", "content": prompt},
        ],
        "temperature": 0.2,
        "max_tokens": 1024,
    }).encode()
    req = urllib.request.Request(
        f"{OPENAI_BASE_URL}/chat/completions",
        data=payload,
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {OPENAI_API_KEY}",
            # FPT sits behind Cloudflare, which 403s the default urllib User-Agent.
            "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
                          "(KHTML, like Gecko) Chrome/124.0 Safari/537.36",
        },
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        result = json.loads(resp.read().decode())
    return json.loads(result["choices"][0]["message"]["content"])


# ── helpers ────────────────────────────────────────────────────────────────────────
def _normalized(profile: dict) -> dict:
    """Extract the `normalized` dict from a full entity, a {"profile": {...}} wrapper,
    or a bare normalized dict."""
    profile = profile or {}
    prof = profile.get("profile")
    if isinstance(prof, dict):
        inner = prof.get("normalized")
        return inner if isinstance(inner, dict) else prof
    inner = profile.get("normalized")
    if isinstance(inner, dict):
        return inner
    return profile


def _as_list(v) -> list:
    if v is None:
        return []
    return list(v) if isinstance(v, (list, tuple, set)) else [v]


def _lower(values) -> list[str]:
    return [str(v).lower().strip() for v in values if v is not None and str(v).strip()]


def _regions(norm: dict) -> list:
    out: list = []
    for key in ("target_regions", "geographies", "regions", "geo", "region", "location"):
        v = norm.get(key)
        if isinstance(v, (list, tuple, set)):
            out += list(v)
        elif v:
            out.append(v)
    return out


def _num(v) -> float | None:
    try:
        return None if v is None else float(v)
    except (TypeError, ValueError):
        return None
