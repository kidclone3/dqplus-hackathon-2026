"""Port of src/services/matching.service.js — keep query/scoring behavior identical."""

import json

from fastapi import HTTPException

from app import config
from app.db import get_pool
from app.services.scoring import score_match


async def find_matches(user_id: str, target_role: str, limit: int, filters: dict | None = None) -> dict:
    filters = filters or {}
    pool = get_pool()

    me_rows = await pool.fetch(
        "SELECT role, attributes FROM extracted_profiles WHERE user_id = $1", user_id
    )
    if not me_rows:
        raise HTTPException(
            status_code=404, detail="No extracted profile for user; run extraction first"
        )
    me = me_rows[0]
    me_role = me["role"]
    me_attrs = json.loads(me["attributes"])

    conditions = ["ep.role = $2", "ep.user_id <> $1"]
    params = [user_id, target_role]

    sector_key = "sectors" if target_role == "investor" else "industry"
    stage_key = "stages" if target_role == "investor" else "stage"
    region_key = "geographies" if target_role == "investor" else "target_regions"

    if filters.get("sector"):
        params.append(filters["sector"].lower())
        conditions.append(f"ep.attributes->'{sector_key}' ? ${len(params)}")
    if filters.get("stage"):
        params.append(filters["stage"].lower())
        if target_role == "investor":
            conditions.append(f"ep.attributes->'{stage_key}' ? ${len(params)}")
        else:
            conditions.append(f"ep.attributes->>'{stage_key}' = ${len(params)}")
    if filters.get("region"):
        params.append(filters["region"].lower())
        conditions.append(f"ep.attributes->'{region_key}' ? ${len(params)}")

    query = f"""
        WITH me AS (
          SELECT embedding FROM extracted_profiles WHERE user_id = $1
        )
        SELECT ep.user_id, ep.attributes,
               1 - (ep.embedding <=> me.embedding) AS vector_score
        FROM extracted_profiles ep, me
        WHERE {' AND '.join(conditions)}
        ORDER BY ep.embedding <=> me.embedding
        LIMIT {config.MATCH_CANDIDATE_POOL}
    """
    candidates = await pool.fetch(query, *params)

    matches = []
    for c in candidates:
        vector_score = float(c["vector_score"])
        candidate_attrs = json.loads(c["attributes"])
        scored = score_match(me_role, me_attrs, candidate_attrs)
        attribute_score = scored["attributeScore"]
        matches.append(
            {
                "userId": c["user_id"],
                "score": round(
                    config.MATCH_VECTOR_WEIGHT * vector_score
                    + config.MATCH_ATTR_WEIGHT * attribute_score,
                    4,
                ),
                "vectorScore": round(vector_score, 4),
                "attributeScore": round(attribute_score, 4),
                "attributes": candidate_attrs,
                "reasons": scored["reasons"],
            }
        )

    matches.sort(key=lambda m: m["score"], reverse=True)
    matches = matches[:limit]

    return {"userId": user_id, "role": me_role, "matches": matches}
