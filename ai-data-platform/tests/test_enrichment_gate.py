"""Enrichment gate unit tests. Pure, no DB.

The `link` stage must mark entities whose enrichment found no verifiable data as
`status='unverified'` (not `'ready'`) so matching — which only pulls ready entities —
skips them. Regression guard for the Touchstone Partners case: a nonexistent seed
(NXDOMAIN domain, no corroborating source) that was persisted as 'ready' and entered
matching with an all-null profile.
"""
from apps.matchmaker.plugin import _count_populated, _enrichment_failed


def _field(value):
    return {"value": value, "confidence": "unavailable" if value is None else "high",
            "source_url": None if value is None else "https://src"}


def test_not_found_verdict_is_failed():
    # Touchstone shape: all fields null + explicit not_found verdict.
    enrichment = {
        "entity_type": "investor",
        "description": _field(None),
        "headquarters": _field(None),
        "relationships": [],
        "collection_summary": {"status": "not_found", "finding": "domain NXDOMAIN"},
    }
    assert _enrichment_failed(enrichment) is True


def test_all_null_without_verdict_is_failed():
    enrichment = {
        "entity_type": "startup",
        "company": {"website": _field(None), "founded": _field(None)},
        "relationships": [],
        "collection_summary": {"sources_used": []},
    }
    assert _enrichment_failed(enrichment) is True


def test_nested_real_data_is_not_failed():
    # Pegasus/Openspace shape: real values nested under arbitrary keys.
    enrichment = {
        "entity_type": "investor",
        "contact": {"email": _field("a@b.com")},
        "basic_info": {"name": _field("Pegasus")},
        "collection_summary": {"sources_used": ["pegasus.com"]},
    }
    assert _enrichment_failed(enrichment) is False


def test_relationships_alone_keep_entity():
    # No provenance fields, but a surfaced edge is real signal.
    enrichment = {
        "entity_type": "investor",
        "relationships": [{"kind": "invested_in", "dst_name": "X"}],
        "collection_summary": {},
    }
    assert _enrichment_failed(enrichment) is False


def test_count_populated_ignores_empty_values():
    assert _count_populated({"f": _field(None)}) == 0
    assert _count_populated({"f": _field("")}) == 0
    assert _count_populated({"f": _field([])}) == 0
    assert _count_populated({"f": _field("real")}) == 1
