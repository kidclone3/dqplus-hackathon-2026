"""Cold-boot scaffolding (R4): idempotent migration runner + seed loader.

Loads seed/*.json → upserts entities (deterministic slug ids, status='seeded') →
creates one onboarding saga per entity → enqueues its `enrich` job. Re-runnable:
slug ids + ON CONFLICT make every write idempotent.

Usage:
  uv run python scripts/bootstrap.py                       # all seed types
  uv run python scripts/bootstrap.py --types startup --limit 3
  uv run python scripts/bootstrap.py --migrate-only
"""
from __future__ import annotations

import argparse
import asyncio
import json
import sys
import uuid
from pathlib import Path

import asyncpg

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))  # run directly: `uv run python scripts/bootstrap.py`

from apps.matchmaker.store import MatchmakerStore as Store
from spine import config
from spine.ids import entity_id

MIGRATIONS_DIR = ROOT / "migrations"
SEED_DIR = ROOT / "seed"


def _migration_files() -> list[Path]:
    """Platform migrations first, then every app's domain migrations (Seam 3)."""
    return (sorted(MIGRATIONS_DIR.glob("*.sql"))
            + sorted(ROOT.glob("apps/*/migrations/*.sql")))


async def run_migrations(conn: asyncpg.Connection) -> list[str]:
    """R13: idempotent migration runner (don't rely solely on initdb)."""
    await conn.execute(
        "CREATE TABLE IF NOT EXISTS schema_migrations ("
        " filename TEXT PRIMARY KEY, applied_at TIMESTAMPTZ NOT NULL DEFAULT now())"
    )
    applied = {r["filename"] for r in await conn.fetch("SELECT filename FROM schema_migrations")}
    newly: list[str] = []
    for path in _migration_files():
        key = str(path.relative_to(ROOT))  # namespaced so app/platform names never collide
        # Legacy DBs recorded the bare basename (e.g. '001_core.sql'); treat those as
        # applied so an upgrade doesn't re-run 001–003 and leave a duplicate ledger.
        if key in applied or path.name in applied:
            continue
        async with conn.transaction():
            await conn.execute(path.read_text())
            await conn.execute(
                "INSERT INTO schema_migrations (filename) VALUES ($1) ON CONFLICT DO NOTHING",
                key,
            )
        newly.append(key)
    return newly


def _seed_records(types: set[str] | None) -> list[dict]:
    """Flatten seed/*.json into {name, type, ...hints} records."""
    records: list[dict] = []
    for path in sorted(SEED_DIR.glob("*.json")):
        doc = json.loads(path.read_text())
        default_type = doc.get("entity_type")
        items = next((v for v in doc.values() if isinstance(v, list)), [])
        for item in items:
            rec = dict(item)
            rec["type"] = rec.get("type") or default_type
            if types and rec["type"] not in types:
                continue
            records.append(rec)
    return records


async def seed(store: Store, records: list[dict], trace_id: str) -> dict:
    entities = sagas_created = jobs_enqueued = 0
    for rec in records:
        name = rec["name"]
        type_ = rec["type"]
        eid = entity_id(type_, name)
        profile = {k: v for k, v in rec.items() if k not in ("name", "type")}
        await store.upsert_entity(eid, type_, name, profile=profile, status="seeded")
        entities += 1

        saga_id = f"onboard:{eid}"
        await store.create_saga(saga_id, "onboarding", eid,
                                current_step="enrich", trace_id=trace_id)
        sagas_created += 1
        jid = await store.enqueue_job(saga_id, "enrich", target_id=eid,
                                      agent="enricher", input_ref={"seed": profile},
                                      trace_id=trace_id)
        if jid is not None:
            jobs_enqueued += 1
    return {"entities": entities, "sagas": sagas_created, "jobs_enqueued": jobs_enqueued}


async def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--types", help="comma list e.g. startup,investor (default: all)")
    ap.add_argument("--names", help="comma list of name substrings (case-insensitive) to "
                                    "onboard a targeted subset, e.g. 'enfarm,Touchstone'")
    ap.add_argument("--limit", type=int, help="max entities to enqueue")
    ap.add_argument("--migrate-only", action="store_true")
    args = ap.parse_args()

    conn = await asyncpg.connect(config.DATABASE_URL)
    try:
        newly = await run_migrations(conn)
        print(f"migrations: {'applied ' + ', '.join(newly) if newly else 'up-to-date'}")
    finally:
        await conn.close()
    if args.migrate_only:
        return

    types = set(args.types.split(",")) if args.types else None
    records = _seed_records(types)
    if args.names:
        wanted = [n.strip().lower() for n in args.names.split(",") if n.strip()]
        records = [r for r in records
                   if any(w in r["name"].lower() for w in wanted)]
    if args.limit:
        records = records[: args.limit]

    trace_id = "run:" + uuid.uuid4().hex[:12]
    store = await Store.connect()
    try:
        stats = await seed(store, records, trace_id)
    finally:
        await store.close()
    print(f"trace_id={trace_id} seeded {stats}")


if __name__ == "__main__":
    asyncio.run(main())
