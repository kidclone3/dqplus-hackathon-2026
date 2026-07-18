import asyncpg

from app import config

# Statements are executed one at a time (never batched into one multi-statement
# string) so that the ALTER TYPE ... ADD VALUE step runs on its own, outside of
# any implicit multi-statement transaction.
CREATE_ENUM_SQL = """
DO $$ BEGIN
    CREATE TYPE enum_users_role AS ENUM ('founder', 'investor');
EXCEPTION
    WHEN duplicate_object THEN null;
END $$;
"""

ADD_ADMIN_VALUE_SQL = "ALTER TYPE enum_users_role ADD VALUE IF NOT EXISTS 'admin';"

CREATE_PROFILES_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS profiles (
    id uuid PRIMARY KEY,
    company_name varchar(255) NOT NULL,
    country varchar(255),
    stage varchar(255),
    num_of_employees integer,
    industry varchar(255),
    target_region varchar(255),
    arr numeric(18, 2),
    where_you_operate varchar(255),
    website varchar(255)[] DEFAULT ARRAY[]::varchar(255)[],
    description_product varchar(255),
    checks varchar(255),
    email varchar(255),
    phone_number varchar(255),
    avg_initial_investment numeric(18, 2),
    annual_investment_count integer,
    avg_holding_period numeric(5, 2),
    year_founded integer,
    created_at timestamptz NOT NULL,
    updated_at timestamptz NOT NULL
);
"""

CREATE_USERS_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS users (
    id uuid PRIMARY KEY,
    username varchar(255) NOT NULL UNIQUE,
    password varchar(255) NOT NULL,
    dob date,
    profile_id uuid REFERENCES profiles(id) ON UPDATE CASCADE ON DELETE SET NULL,
    role enum_users_role NOT NULL,
    created_at timestamptz NOT NULL,
    updated_at timestamptz NOT NULL
);
"""


async def create_pool() -> asyncpg.Pool:
    ssl = "require" if config.DB_SSL else None
    return await asyncpg.create_pool(
        host=config.DB_HOST,
        port=config.DB_PORT,
        database=config.DB_NAME,
        user=config.DB_USER,
        password=config.DB_PASSWORD,
        ssl=ssl,
    )


async def bootstrap_schema(pool: asyncpg.Pool) -> None:
    async with pool.acquire() as conn:
        await conn.execute(CREATE_ENUM_SQL)
        await conn.execute(ADD_ADMIN_VALUE_SQL)
        await conn.execute(CREATE_PROFILES_TABLE_SQL)
        await conn.execute(CREATE_USERS_TABLE_SQL)
