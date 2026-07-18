"""Deterministic fixture seed + in-process bootstrap for the North Star harness.

Mirrors scripts/bootstrap.py's enqueue shape (one onboarding saga + enrich job per
entity) but in-process against an injected Store, using a tiny fixed seed so A1–A5
counts are deterministic.
"""
from __future__ import annotations

from spine.ids import entity_id

STARTUPS = [
    {"name": "Alpha AI", "sectors": ["ai"]},
    {"name": "Beta Robotics", "sectors": ["ai"]},
    {"name": "Gamma Health", "sectors": ["ai"]},
]
PARTNERS = [
    {"name": "Seed Capital VN", "type": "investor", "sectors": ["ai"]},
    {"name": "North Fund", "type": "investor", "sectors": ["ai"]},
    {"name": "Delta Ventures", "type": "investor", "sectors": ["ai"]},
    {"name": "MegaCorp", "type": "corporation", "sectors": ["ai"]},
    {"name": "IndusTech", "type": "corporation", "sectors": ["ai"]},
    {"name": "Hanoi University", "type": "university", "sectors": ["ai"]},
    {"name": "Danang Institute", "type": "university", "sectors": ["ai"]},
    {"name": "National Research Lab", "type": "research_institution", "sectors": ["ai"]},
]

STARTUP_COUNT = len(STARTUPS)
PARTNER_COUNT = len(PARTNERS)
ENTITY_COUNT = STARTUP_COUNT + PARTNER_COUNT


async def seed_and_enqueue_onboarding(store) -> list[str]:
    """Upsert entities (status='seeded') + one onboarding saga + enrich job each.
    Returns the startup ids. Idempotent (deterministic slug ids, ON CONFLICT)."""
    startup_ids: list[str] = []
    for rec in STARTUPS + PARTNERS:
        typ = rec.get("type", "startup")
        eid = entity_id(typ, rec["name"])
        await store.upsert_entity(eid, typ, rec["name"],
                                  profile={"sectors": rec["sectors"]}, status="seeded")
        saga_id = f"onboarding:{eid}"
        await store.create_saga(saga_id, "onboarding", eid, current_step="enrich")
        await store.enqueue_job(saga_id, "enrich", target_id=eid, agent="enricher")
        if typ == "startup":
            startup_ids.append(eid)
    return startup_ids


async def enqueue_outreach(store, startup_ids: list[str]) -> None:
    """Mirror scripts/outreach.py: one outreach saga + filter job per startup."""
    for sid in startup_ids:
        saga_id = f"outreach:{sid}"
        await store.create_saga(saga_id, "outreach", sid, current_step="filter")
        await store.enqueue_job(saga_id, "filter", target_id=sid, agent=None)
