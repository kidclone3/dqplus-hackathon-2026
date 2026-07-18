"""Backfill entities.embedding (EmbeddingMatcher, migration 004_embeddings.sql).

Selects entities missing an embedding (or all with --all), computes each vector via
`spine.embedding.embed_text(entity_text(row))`, and writes it back as a pgvector
literal. Idempotent: default run only touches rows WHERE embedding IS NULL, so it can
be re-run after seeding/enrichment to fill in the gaps.

Usage:
  uv run python scripts/embed_entities.py                    # backfill NULL embeddings
  uv run python scripts/embed_entities.py --all              # recompute every entity
  uv run python scripts/embed_entities.py --types startup,investor
  uv run python scripts/embed_entities.py --batch-size 50 --limit 20
"""
from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from spine import embedding, telemetry
from spine.store import Store

log = telemetry.get_logger("embed_entities")


def _to_pgvector(vec: list[float]) -> str:
    """pgvector text literal, e.g. '[0.1,0.2,...]' (bound as $1::vector)."""
    return "[" + ",".join(str(float(x)) for x in vec) + "]"


def _row_entity(row) -> dict:
    """Normalize an asyncpg row into the entity dict entity_text() expects."""
    d = dict(row)
    profile = d.get("profile")
    d["profile"] = json.loads(profile) if isinstance(profile, str) else (profile or {})
    return d


async def backfill(store: Store, *, all_: bool, types: set[str] | None,
                   limit: int | None, batch_size: int) -> dict:
    where = [] if all_ else ["embedding IS NULL"]
    params: list = []
    if types:
        params.append(list(types))
        where.append(f"type = ANY(${len(params)})")
    sql = "SELECT id, type, name, profile, status FROM entities"
    if where:
        sql += " WHERE " + " AND ".join(where)
    sql += " ORDER BY id"
    if limit:
        params.append(limit)
        sql += f" LIMIT ${len(params)}"

    rows = await store.pool.fetch(sql, *params)
    total = len(rows)
    log.info("backfill_start", total=total, mode="all" if all_ else "missing",
             embedding_dim=embedding.EMBEDDING_DIM, batch_size=batch_size)

    updated = 0
    for start in range(0, total, batch_size):
        batch = rows[start:start + batch_size]
        for row in batch:
            entity = _row_entity(row)
            vec = await embedding.embed_text(embedding.entity_text(entity))
            await store.pool.execute(
                "UPDATE entities SET embedding = $1::vector, updated_at = now() WHERE id = $2",
                _to_pgvector(vec), entity["id"],
            )
            updated += 1
        log.info("backfill_progress", updated=updated, total=total)

    log.info("backfill_done", updated=updated, total=total)
    return {"updated": updated, "total": total}


async def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--all", action="store_true",
                    help="recompute every entity (default: only embedding IS NULL)")
    ap.add_argument("--types", help="comma list e.g. startup,investor (default: all)")
    ap.add_argument("--limit", type=int, help="max entities to embed")
    ap.add_argument("--batch-size", type=int, default=100, help="rows per progress batch")
    args = ap.parse_args()

    telemetry.configure()
    types = set(args.types.split(",")) if args.types else None
    store = await Store.connect()
    try:
        stats = await backfill(store, all_=args.all, types=types,
                               limit=args.limit, batch_size=args.batch_size)
    finally:
        await store.close()
    print(f"embedded {stats}")


if __name__ == "__main__":
    asyncio.run(main())
