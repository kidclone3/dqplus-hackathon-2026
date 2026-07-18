import asyncio
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any
from uuid import uuid4

import asyncpg
import httpx

from app import config
from app.errors import ServiceError
from app.serializers import decimal_str, js_iso

PROFILE_FIELDS = [
    "company_name",
    "country",
    "stage",
    "num_of_employees",
    "industry",
    "target_region",
    "arr",
    "where_you_operate",
    "website",
    "description_product",
    "checks",
    "email",
    "phone_number",
    "avg_initial_investment",
    "annual_investment_count",
    "avg_holding_period",
    "year_founded",
]

NUMERIC_FIELDS = {"arr", "avg_initial_investment", "avg_holding_period"}


def _to_param(key: str, value: Any) -> Any:
    if value is not None and key in NUMERIC_FIELDS:
        return Decimal(str(value))
    return value


def _serialize(row: asyncpg.Record) -> dict:
    return {
        "id": str(row["id"]),
        "company_name": row["company_name"],
        "country": row["country"],
        "stage": row["stage"],
        "num_of_employees": row["num_of_employees"],
        "industry": row["industry"],
        "target_region": row["target_region"],
        "arr": decimal_str(row["arr"]),
        "where_you_operate": row["where_you_operate"],
        "website": list(row["website"]) if row["website"] is not None else [],
        "description_product": row["description_product"],
        "checks": row["checks"],
        "email": row["email"],
        "phone_number": row["phone_number"],
        "avg_initial_investment": decimal_str(row["avg_initial_investment"]),
        "annual_investment_count": row["annual_investment_count"],
        "avg_holding_period": decimal_str(row["avg_holding_period"]),
        "year_founded": row["year_founded"],
        "createdAt": js_iso(row["created_at"]),
        "updatedAt": js_iso(row["updated_at"]),
    }


def _trigger_extraction(user_id: str) -> None:
    if not config.EXTRACT_SERVICE_URL:
        return

    async def _send() -> None:
        try:
            async with httpx.AsyncClient(timeout=8.0) as client:
                await client.post(
                    f"{config.EXTRACT_SERVICE_URL}/extract/profile",
                    json={"userId": user_id},
                )
        except Exception as err:
            print(f"extract trigger failed: {err}")

    asyncio.create_task(_send())


async def create_profile(pool: asyncpg.Pool, user_id: str, data: dict) -> dict:
    async with pool.acquire() as conn:
        user = await conn.fetchrow("SELECT id, profile_id FROM users WHERE id = $1", user_id)
        if not user:
            raise ServiceError(404, "User not found")
        if user["profile_id"]:
            raise ServiceError(409, "User already has a profile")

        profile_id = str(uuid4())
        now = datetime.now(timezone.utc)
        website = data.get("website")
        if website is None:
            website = []

        row = await conn.fetchrow(
            """
            INSERT INTO profiles (
                id, company_name, country, stage, num_of_employees, industry,
                target_region, arr, where_you_operate, website, description_product,
                checks, email, phone_number, avg_initial_investment,
                annual_investment_count, avg_holding_period, year_founded,
                created_at, updated_at
            ) VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13,$14,$15,$16,$17,$18,$19,$19)
            RETURNING *
            """,
            profile_id,
            data.get("company_name"),
            data.get("country"),
            data.get("stage"),
            data.get("num_of_employees"),
            data.get("industry"),
            data.get("target_region"),
            _to_param("arr", data.get("arr")),
            data.get("where_you_operate"),
            website,
            data.get("description_product"),
            data.get("checks"),
            data.get("email"),
            data.get("phone_number"),
            _to_param("avg_initial_investment", data.get("avg_initial_investment")),
            data.get("annual_investment_count"),
            _to_param("avg_holding_period", data.get("avg_holding_period")),
            data.get("year_founded"),
            now,
        )

        await conn.execute(
            "UPDATE users SET profile_id = $1, updated_at = $2 WHERE id = $3",
            profile_id,
            now,
            user_id,
        )

    _trigger_extraction(user_id)
    return _serialize(row)


async def update_profile(pool: asyncpg.Pool, user_id: str, profile_id: str, data: dict) -> dict:
    async with pool.acquire() as conn:
        user = await conn.fetchrow("SELECT id, profile_id FROM users WHERE id = $1", user_id)
        if not user or user["profile_id"] is None or str(user["profile_id"]) != profile_id:
            raise ServiceError(403, "Forbidden")

        profile = await conn.fetchrow("SELECT * FROM profiles WHERE id = $1", profile_id)
        if not profile:
            raise ServiceError(404, "Profile not found")

        now = datetime.now(timezone.utc)
        set_clauses = []
        params = []
        idx = 1
        for key in PROFILE_FIELDS:
            if key in data:
                set_clauses.append(f"{key} = ${idx}")
                params.append(_to_param(key, data[key]))
                idx += 1
        set_clauses.append(f"updated_at = ${idx}")
        params.append(now)
        idx += 1
        params.append(profile_id)

        row = await conn.fetchrow(
            f"UPDATE profiles SET {', '.join(set_clauses)} WHERE id = ${idx} RETURNING *",
            *params,
        )

    _trigger_extraction(user_id)
    return _serialize(row)


async def get_profile(pool: asyncpg.Pool, profile_id: str) -> dict:
    async with pool.acquire() as conn:
        row = await conn.fetchrow("SELECT * FROM profiles WHERE id = $1", profile_id)
    if not row:
        raise ServiceError(404, "Profile not found")
    return _serialize(row)
