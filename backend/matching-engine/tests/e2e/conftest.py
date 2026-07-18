import json
import os
import uuid

import asyncpg
import httpx
import pytest
import pytest_asyncio

from app import config

# Real Postgres + pgvector under test, overridable via env for other setups.
TEST_DB_HOST = os.environ.get("TEST_DB_HOST", os.environ.get("DB_HOST", "localhost"))
TEST_DB_PORT = int(os.environ.get("TEST_DB_PORT", os.environ.get("DB_PORT", "5434")))
TEST_DB_NAME = os.environ.get("TEST_DB_NAME", os.environ.get("DB_NAME", "dealflow"))
TEST_DB_USER = os.environ.get("TEST_DB_USER", os.environ.get("DB_USER", "dealflow"))
TEST_DB_PASSWORD = os.environ.get("TEST_DB_PASSWORD", os.environ.get("DB_PASSWORD", "dealflow"))

# The app reads `config.<NAME>` at call time (not at import time), so patching the
# module's attributes here takes effect for every request made through the app.
config.DB_HOST = TEST_DB_HOST
config.DB_PORT = TEST_DB_PORT
config.DB_NAME = TEST_DB_NAME
config.DB_USER = TEST_DB_USER
config.DB_PASSWORD = TEST_DB_PASSWORD
config.DB_SSL = False
config.MATCH_VECTOR_WEIGHT = 0.7
config.MATCH_ATTR_WEIGHT = 0.3
config.MATCH_CANDIDATE_POOL = 50

from app.main import app, lifespan  # noqa: E402  (must import after config overrides above)

DDL = """
CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE IF NOT EXISTS extracted_profiles (
  id             UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id        UUID NOT NULL UNIQUE,
  role           TEXT NOT NULL CHECK (role IN ('founder', 'investor')),
  source         TEXT NOT NULL CHECK (source IN ('text', 'crawler', 'profile')),
  source_url     TEXT,
  raw_input      TEXT,
  attributes     JSONB NOT NULL DEFAULT '{}'::jsonb,
  embedding_text TEXT NOT NULL,
  embedding      vector(1536) NOT NULL,
  created_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at     TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_extracted_profiles_role
  ON extracted_profiles (role);

CREATE INDEX IF NOT EXISTS idx_extracted_profiles_embedding
  ON extracted_profiles USING hnsw (embedding vector_cosine_ops);
"""


def vector_literal(nonzero: dict, dim: int = 1536) -> str:
    """Build a pgvector text literal like '[0,1,0,...]' from a sparse {index: value} map."""
    values = ["0"] * dim
    for i, v in nonzero.items():
        values[i] = repr(v)
    return "[" + ",".join(values) + "]"


@pytest_asyncio.fixture
async def db_conn():
    conn = await asyncpg.connect(
        host=TEST_DB_HOST,
        port=TEST_DB_PORT,
        database=TEST_DB_NAME,
        user=TEST_DB_USER,
        password=TEST_DB_PASSWORD,
    )
    await conn.execute(DDL)
    yield conn
    await conn.close()


async def seed_profile(conn, user_id, role, attributes, embedding_vec, source="text"):
    await conn.execute(
        """
        INSERT INTO extracted_profiles (user_id, role, source, attributes, embedding_text, embedding)
        VALUES ($1, $2, $3, $4::jsonb, $5, $6::vector)
        """,
        uuid.UUID(user_id),
        role,
        source,
        json.dumps(attributes),
        f"seed:{user_id}",
        embedding_vec,
    )


async def delete_profile(conn, user_id):
    await conn.execute(
        "DELETE FROM extracted_profiles WHERE user_id = $1", uuid.UUID(user_id)
    )


@pytest_asyncio.fixture
async def client():
    # httpx.ASGITransport does not itself drive ASGI lifespan events, so the
    # app's lifespan context manager (pool connect/disconnect) is driven manually.
    async with lifespan(app):
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as ac:
            yield ac
