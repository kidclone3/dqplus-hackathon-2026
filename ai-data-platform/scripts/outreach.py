"""Trigger the outreach saga (spec §6 Saga 2) for onboarded startups.

Creates one outreach saga per ready startup and enqueues its `filter` job; the running
supervisor drains filter -> match -> draft -> verify. Idempotent (saga_id + job keys).

Usage:
  uv run python scripts/outreach.py --startup startup:enfarm-agritech
  uv run python scripts/outreach.py --all            # every ready startup
"""
from __future__ import annotations

import argparse
import asyncio
import sys
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from apps.matchmaker.store import MatchmakerStore as Store


async def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--startup", help="entity id, e.g. startup:enfarm-agritech")
    ap.add_argument("--all", action="store_true", help="all ready startups")
    args = ap.parse_args()

    trace_id = "run:" + uuid.uuid4().hex[:12]
    store = await Store.connect()
    try:
        if args.all:
            rows = await store.pool.fetch(
                "SELECT id FROM entities WHERE type = 'startup' AND status = 'ready' ORDER BY id"
            )
            ids = [r["id"] for r in rows]
        elif args.startup:
            ids = [args.startup]
        else:
            ap.error("pass --startup <id> or --all")

        for sid in ids:
            saga_id = f"outreach:{sid}"
            await store.create_saga(saga_id, "outreach", sid,
                                    current_step="filter", trace_id=trace_id)
            await store.enqueue_job(saga_id, "filter", target_id=sid, trace_id=trace_id)
            print(f"triggered {saga_id}")
        print(f"trace_id={trace_id} started {len(ids)} outreach saga(s)")
    finally:
        await store.close()


if __name__ == "__main__":
    asyncio.run(main())
