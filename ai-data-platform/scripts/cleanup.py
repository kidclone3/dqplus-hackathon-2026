"""Trigger a cleanup saga for entities matching an id prefix, then drain it.

Usage (source .env first — spine reads os.environ):
    uv run python scripts/cleanup.py --prefix 'startup:saga_' [--enqueue-only]

Runs a supervisor restricted to the cleanup stages so stale ready jobs from the
onboarding/outreach sagas are NOT leased (and no LLM spend happens on them).
"""
from __future__ import annotations

import argparse
import asyncio
import sys
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from spine import cleanup, telemetry
from spine.store import Store
from spine.supervisor import Supervisor


async def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--prefix", required=True, help="entity id prefix to audit")
    ap.add_argument("--enqueue-only", action="store_true",
                    help="enqueue the saga without running the supervisor")
    args = ap.parse_args()

    telemetry.configure()
    log = telemetry.get_logger("cleanup")
    store = await Store.connect()
    try:
        trace_id = "cleanup:" + uuid.uuid4().hex[:12]
        saga_id, n = await cleanup.start(store, args.prefix, trace_id=trace_id)
        log.info("cleanup_enqueued", saga_id=saga_id, candidates=n, trace_id=trace_id)
        if n == 0:
            log.info("no_candidates", prefix=args.prefix)
            return
        if args.enqueue_only:
            return
        sup = Supervisor(store, stages=list(cleanup.CLEANUP_STAGES))
        await sup.run(drain=True)
    finally:
        await store.close()


if __name__ == "__main__":
    asyncio.run(main())
