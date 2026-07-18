import ssl

import asyncpg

from app import config

_pool: asyncpg.Pool | None = None


def _ssl_context() -> ssl.SSLContext | None:
    if not config.DB_SSL:
        return None
    # Mirrors the Node config's `{ rejectUnauthorized: false }`.
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    return ctx


async def connect() -> asyncpg.Pool:
    global _pool
    _pool = await asyncpg.create_pool(
        host=config.DB_HOST,
        port=config.DB_PORT,
        database=config.DB_NAME,
        user=config.DB_USER,
        password=config.DB_PASSWORD,
        ssl=_ssl_context(),
        min_size=0,
    )
    return _pool


async def disconnect() -> None:
    global _pool
    if _pool is not None:
        await _pool.close()
        _pool = None


def get_pool() -> asyncpg.Pool:
    if _pool is None:
        raise RuntimeError("Database pool is not initialized")
    return _pool
