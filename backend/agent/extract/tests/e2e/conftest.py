import os
import uuid

import asyncpg
import httpx
import pytest

# Real Postgres+pgvector fixture (dqplus-test-postgres, docker-compose test service),
# not mocked. Force keyless mode so the extraction/embedding pipeline runs the local
# feature-hash fallback deterministically without needing an LLM API key.
os.environ.setdefault("DB_HOST", "localhost")
os.environ.setdefault("DB_PORT", "5434")
os.environ.setdefault("DB_NAME", "dealflow")
os.environ.setdefault("DB_USER", "dealflow")
os.environ.setdefault("DB_PASSWORD", "dealflow")
os.environ["OPENAI_API_KEY"] = ""

from app import config, db  # noqa: E402
from app.main import app  # noqa: E402

# Mirrors backend/gateway's Sequelize models (users.model.js / profile.model.js)
# so /extract/profile has real users+profiles rows to join against.
USERS_ENUM_DDL = """
DO $$ BEGIN
    CREATE TYPE enum_users_role AS ENUM ('founder', 'investor');
EXCEPTION WHEN duplicate_object THEN NULL;
END $$;
"""

USERS_TABLE_DDL = """
CREATE TABLE IF NOT EXISTS users (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  username VARCHAR NOT NULL UNIQUE,
  password VARCHAR NOT NULL,
  dob DATE,
  profile_id UUID,
  role enum_users_role NOT NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
"""

PROFILES_TABLE_DDL = """
CREATE TABLE IF NOT EXISTS profiles (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  company_name VARCHAR NOT NULL,
  country VARCHAR,
  stage VARCHAR,
  num_of_employees INTEGER,
  industry VARCHAR,
  target_region VARCHAR,
  arr NUMERIC(18, 2),
  where_you_operate VARCHAR,
  website VARCHAR[] DEFAULT '{}',
  description_product VARCHAR,
  checks VARCHAR,
  email VARCHAR,
  phone_number VARCHAR,
  avg_initial_investment NUMERIC(18, 2),
  annual_investment_count INTEGER,
  avg_holding_period NUMERIC(5, 2),
  year_founded INTEGER,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
"""


@pytest.fixture(scope="session", autouse=True)
async def _schema():
    conn = await asyncpg.connect(
        host=config.DB_HOST,
        port=config.DB_PORT,
        database=config.DB_NAME,
        user=config.DB_USER,
        password=config.DB_PASSWORD,
    )
    await conn.execute(USERS_ENUM_DDL)
    try:
        await conn.execute("ALTER TYPE enum_users_role ADD VALUE IF NOT EXISTS 'admin'")
    except asyncpg.PostgresError:
        pass
    await conn.execute(USERS_TABLE_DDL)
    await conn.execute(PROFILES_TABLE_DDL)
    await conn.execute(db.SCHEMA_PATH.read_text())
    await conn.close()
    yield


@pytest.fixture
async def client():
    async with app.router.lifespan_context(app):
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
            yield c


@pytest.fixture
async def db_conn():
    conn = await asyncpg.connect(
        host=config.DB_HOST,
        port=config.DB_PORT,
        database=config.DB_NAME,
        user=config.DB_USER,
        password=config.DB_PASSWORD,
    )
    yield conn
    await conn.close()


@pytest.fixture
async def seeded_founder(db_conn):
    """Creates a users+profiles row pair for a founder, cleans up after the test."""
    profile_id = str(uuid.uuid4())
    user_id = str(uuid.uuid4())
    await db_conn.execute(
        """INSERT INTO profiles (id, company_name, country, stage, num_of_employees, industry,
                                  target_region, arr, description_product, checks, created_at, updated_at)
           VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, now(), now())""",
        profile_id,
        "Acme AI",
        "Vietnam",
        "series_a",
        18,
        "Fintech, AI",
        "Vietnam, Singapore",
        1200000,
        "AI-powered fraud detection platform",
        "500k",
    )
    await db_conn.execute(
        """INSERT INTO users (id, username, password, profile_id, role, created_at, updated_at)
           VALUES ($1, $2, 'x', $3, 'founder', now(), now())""",
        user_id,
        f"founder-{user_id}",
        profile_id,
    )
    yield user_id
    await db_conn.execute("DELETE FROM extracted_profiles WHERE user_id = $1", user_id)
    await db_conn.execute("DELETE FROM users WHERE id = $1", user_id)
    await db_conn.execute("DELETE FROM profiles WHERE id = $1", profile_id)


@pytest.fixture
async def seeded_investor(db_conn):
    profile_id = str(uuid.uuid4())
    user_id = str(uuid.uuid4())
    await db_conn.execute(
        """INSERT INTO profiles (id, company_name, industry, stage, target_region,
                                  description_product, avg_initial_investment, created_at, updated_at)
           VALUES ($1, $2, $3, $4, $5, $6, $7, now(), now())""",
        profile_id,
        "Golden Gate Ventures",
        "Fintech, SaaS",
        "seed",
        "Southeast Asia",
        "VC firm investing in early-stage startups",
        250000,
    )
    await db_conn.execute(
        """INSERT INTO users (id, username, password, profile_id, role, created_at, updated_at)
           VALUES ($1, $2, 'x', $3, 'investor', now(), now())""",
        user_id,
        f"investor-{user_id}",
        profile_id,
    )
    yield user_id
    await db_conn.execute("DELETE FROM extracted_profiles WHERE user_id = $1", user_id)
    await db_conn.execute("DELETE FROM users WHERE id = $1", user_id)
    await db_conn.execute("DELETE FROM profiles WHERE id = $1", profile_id)


@pytest.fixture
async def cleanup_extracted(db_conn):
    """For tests that insert directly via the API without a seeded users/profiles row."""
    user_ids = []
    yield user_ids
    for uid in user_ids:
        await db_conn.execute("DELETE FROM extracted_profiles WHERE user_id = $1", uid)
