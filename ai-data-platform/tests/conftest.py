import uuid

import asyncpg
import pytest
import pytest_asyncio

from apps.matchmaker.store import MatchmakerStore as Store
from spine import config


async def _db_reachable() -> bool:
    try:
        conn = await asyncpg.connect(config.DATABASE_URL, timeout=3)
        await conn.close()
        return True
    except Exception:
        return False


@pytest_asyncio.fixture
async def store():
    if not await _db_reachable():
        pytest.skip("Postgres not reachable at DATABASE_URL "
                    "(run: docker compose up -d postgres)")
    s = await Store.connect(min_size=1, max_size=4)
    try:
        yield s
    finally:
        await s.close()


@pytest.fixture
def saga_id() -> str:
    """Unique per test so rows never collide across the shared DB."""
    return "saga_" + uuid.uuid4().hex[:12]
