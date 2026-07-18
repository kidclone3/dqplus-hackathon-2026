"""Rule-filter + sector normalization unit tests (R2). Pure, no DB.

Asserts the permissive contract: sector overlap is the only hard drop (and only when
both sides carry sectors); purpose never hard-drops; bilingual tags intersect; the
filter never collapses to zero when candidates plausibly overlap.
"""
from apps.matchmaker.matcher import normalize_sectors, rule_filter


def _partner(pid, type_, *, sectors=None, innovation_areas=None, research_domains=None):
    seed = {}
    if innovation_areas:
        seed["innovation_areas"] = innovation_areas
    if research_domains:
        seed["research_domains"] = research_domains
    profile = {"normalized": {"sectors": sectors} if sectors else {}, "seed": seed}
    return {"id": pid, "type": type_, "name": pid, "profile": profile}


def test_normalize_bilingual_and_canonical():
    assert normalize_sectors(["enterprise_ai", "AI Agents"]) == {"ai"}
    assert normalize_sectors(["clean_energy"]) == {"cleantech"}
    assert normalize_sectors(["nông nghiệp", "agtech"]) == {"agritech"}
    assert normalize_sectors(["fintech"]) == {"fintech"}   # passthrough unknowns
    assert normalize_sectors(None) == set()


def test_sector_overlap_is_the_only_hard_drop():
    startup = {"sectors": ["agritech", "ai"], "looking_for": ["funding"]}
    partners = [
        _partner("investor:a", "investor", sectors=["agritech"]),      # overlap
        _partner("investor:b", "investor", sectors=["fintech"]),       # disjoint -> DROP
    ]
    out = rule_filter(startup, partners)
    ids = {c["partner_id"] for c in out}
    assert ids == {"investor:a"}                                       # b dropped
    assert out[0]["low_confidence_filter"] is False                    # sector + purpose ok


def test_purpose_mismatch_never_drops_only_flags():
    """A funding-only startup keeps sector-overlapping corporations/universities as
    low-confidence candidates (never a hard drop) so the LLM judge can span types."""
    startup = {"sectors": ["ai"], "looking_for": ["funding"]}
    partners = [
        _partner("investor:a", "investor", sectors=["ai"]),
        _partner("corporation:c", "corporation", innovation_areas=["ai"]),
        _partner("university:u", "university", research_domains=["ai"]),
    ]
    out = {c["partner_id"]: c for c in rule_filter(startup, partners)}
    assert set(out) == {"investor:a", "corporation:c", "university:u"}   # nobody dropped
    assert out["investor:a"]["low_confidence_filter"] is False          # purpose matches
    assert out["corporation:c"]["low_confidence_filter"] is True        # purpose flagged
    assert out["university:u"]["low_confidence_filter"] is True


def test_missing_sector_signal_passes_through_low_confidence():
    startup = {"sectors": [], "looking_for": ["funding"]}               # unknown sectors
    partners = [_partner("investor:a", "investor", sectors=["agritech"])]
    out = rule_filter(startup, partners)
    assert len(out) == 1
    assert out[0]["low_confidence_filter"] is True


def test_multi_purpose_startup_matches_multiple_types():
    startup = {"sectors": ["agritech"],
               "looking_for": ["funding", "rd_collaboration", "corporate_pilot"]}
    partners = [
        _partner("investor:a", "investor", sectors=["agritech"]),
        _partner("corporation:c", "corporation", innovation_areas=["agritech"]),
        _partner("research_institution:r", "research_institution", research_domains=["agritech"]),
    ]
    out = {c["partner_id"]: c["purpose_match"] for c in rule_filter(startup, partners)}
    assert out == {"investor:a": True, "corporation:c": True, "research_institution:r": True}
