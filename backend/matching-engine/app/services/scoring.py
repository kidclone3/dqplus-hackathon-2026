"""Port of src/services/scoring.js — keep behavior (including reason strings) identical."""


def jaccard(a: list | None = None, b: list | None = None) -> float:
    a = a or []
    b = b or []
    if not a or not b:
        return 0
    set_a = {str(s).lower() for s in a}
    set_b = {str(s).lower() for s in b}
    intersection = [x for x in set_a if x in set_b]
    union = set_a | set_b
    return len(intersection) / len(union)


def intersect(a: list | None = None, b: list | None = None) -> list[str]:
    a = a or []
    b = b or []
    set_b = {str(s).lower() for s in b}
    return [x for x in (str(s).lower() for s in a) if x in set_b]


# founderAttrs: industry[], stage, target_regions[], funding_ask_usd
# investorAttrs: sectors[], stages[], geographies[], check_size_min_usd, check_size_max_usd
def score_attributes(founder_attrs: dict, investor_attrs: dict) -> dict:
    reasons = []
    score = 0

    sector_overlap = jaccard(founder_attrs.get("industry"), investor_attrs.get("sectors"))
    if sector_overlap > 0:
        score += 0.4 * sector_overlap
        overlap = intersect(founder_attrs.get("industry"), investor_attrs.get("sectors"))
        reasons.append(f"sector overlap: {', '.join(overlap)}")

    founder_stage = founder_attrs.get("stage")
    investor_stages = [str(s).lower() for s in (investor_attrs.get("stages") or [])]
    if founder_stage and str(founder_stage).lower() in investor_stages:
        score += 0.3
        reasons.append(f"stage match: {founder_stage}")

    geos = [str(s).lower() for s in (investor_attrs.get("geographies") or [])]
    regions = [str(s).lower() for s in (founder_attrs.get("target_regions") or [])]
    if "global" in geos and regions:
        score += 0.2
        reasons.append("investor invests globally")
    else:
        geo_overlap = intersect(regions, geos)
        if geo_overlap:
            score += 0.2
            reasons.append(f"geography match: {', '.join(geo_overlap)}")

    ask = founder_attrs.get("funding_ask_usd")
    min_check = investor_attrs.get("check_size_min_usd")
    max_check = investor_attrs.get("check_size_max_usd")
    if ask is not None and (min_check is not None or max_check is not None):
        above_min = min_check is None or ask >= min_check
        below_max = max_check is None or ask <= max_check
        if above_min and below_max:
            score += 0.1 if (min_check is not None and max_check is not None) else 0.05
            reasons.append("check size fits funding ask")

    return {"attributeScore": min(score, 1), "reasons": reasons}


def score_match(requester_role: str, requester_attrs: dict, candidate_attrs: dict) -> dict:
    if requester_role == "founder":
        return score_attributes(requester_attrs, candidate_attrs)
    return score_attributes(candidate_attrs, requester_attrs)
