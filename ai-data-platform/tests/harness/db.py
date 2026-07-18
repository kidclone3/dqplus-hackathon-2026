"""Ephemeral Postgres database for the North Star harness.

Creates a throwaway DB `dealflow_ns_<hex>` on the configured server, applies
migrations/*.sql into it, yields a Store bound to it, and drops it after. Skips
the whole harness if Postgres is unreachable (same policy as tests/conftest.py).
"""
from __future__ import annotations

import uuid
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit

import asyncpg

from apps.matchmaker.store import MatchmakerStore as Store
from spine import config

_ROOT = Path(__file__).resolve().parents[2]
MIGRATIONS_DIR = _ROOT / "migrations"


def _migration_files() -> list[Path]:
    """Platform migrations first, then every app's domain migrations (Seam 3)."""
    return (sorted(MIGRATIONS_DIR.glob("*.sql"))
            + sorted(_ROOT.glob("apps/*/migrations/*.sql")))


def _swap_db(dsn: str, dbname: str) -> str:
    parts = urlsplit(dsn)
    return urlunsplit(parts._replace(path=f"/{dbname}"))


async def db_reachable() -> bool:
    try:
        conn = await asyncpg.connect(config.DATABASE_URL, timeout=3)
        await conn.close()
        return True
    except Exception:
        return False


async def create_ephemeral() -> tuple[str, Store]:
    """Returns (dbname, Store bound to a fresh migrated DB)."""
    dbname = f"dealflow_ns_{uuid.uuid4().hex[:12]}"
    admin = await asyncpg.connect(_swap_db(config.DATABASE_URL, "postgres"))
    try:
        await admin.execute(f'CREATE DATABASE "{dbname}"')
    finally:
        await admin.close()

    dsn = _swap_db(config.DATABASE_URL, dbname)
    conn = await asyncpg.connect(dsn)
    try:
        for path in _migration_files():
            await conn.execute(path.read_text())
    finally:
        await conn.close()

    store = await Store.connect(dsn, min_size=1, max_size=6)
    return dbname, store


async def drop_ephemeral(dbname: str, store: Store) -> None:
    await store.close()
    admin = await asyncpg.connect(_swap_db(config.DATABASE_URL, "postgres"))
    try:
        await admin.execute(
            "SELECT pg_terminate_backend(pid) FROM pg_stat_activity "
            "WHERE datname = $1 AND pid <> pg_backend_pid()", dbname)
        await admin.execute(f'DROP DATABASE IF EXISTS "{dbname}"')
    finally:
        await admin.close()
