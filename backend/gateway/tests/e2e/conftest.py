import os
import uuid

import asyncpg
import httpx
import pytest
from asgi_lifespan import LifespanManager

os.environ.setdefault("DB_HOST", os.environ.get("DB_HOST", "localhost"))
os.environ.setdefault("DB_PORT", os.environ.get("DB_PORT", "5434"))
os.environ.setdefault("DB_NAME", os.environ.get("DB_NAME", "dealflow"))
os.environ.setdefault("DB_USER", os.environ.get("DB_USER", "dealflow"))
os.environ.setdefault("DB_PASSWORD", os.environ.get("DB_PASSWORD", "dealflow"))
os.environ.setdefault("JWT_SECRET", "e2e-test-secret")
os.environ.setdefault("JWT_EXPIRES_IN", "1d")

DB_HOST = os.environ["DB_HOST"]
DB_PORT = int(os.environ["DB_PORT"])
DB_NAME = os.environ["DB_NAME"]
DB_USER = os.environ["DB_USER"]
DB_PASSWORD = os.environ["DB_PASSWORD"]


def unique_username(prefix: str = "user") -> str:
    return f"{prefix}-{uuid.uuid4().hex[:12]}"


@pytest.fixture
async def app():
    from app.main import app as fastapi_app

    async with LifespanManager(fastapi_app) as manager:
        yield manager.app


@pytest.fixture
async def client(app):
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as ac:
        yield ac


@pytest.fixture
async def db_conn():
    conn = await asyncpg.connect(
        host=DB_HOST, port=DB_PORT, database=DB_NAME, user=DB_USER, password=DB_PASSWORD
    )
    yield conn
    await conn.close()
