from datetime import date, datetime, timezone
from uuid import uuid4

import asyncpg

from app import security
from app.errors import ServiceError
from app.serializers import js_iso


def _sanitize(row: asyncpg.Record) -> dict:
    dob = row["dob"]
    return {
        "id": str(row["id"]),
        "username": row["username"],
        "dob": dob.isoformat() if isinstance(dob, date) else None,
        "role": row["role"],
        "profileId": str(row["profile_id"]) if row["profile_id"] else None,
        "createdAt": js_iso(row["created_at"]),
        "updatedAt": js_iso(row["updated_at"]),
    }


async def register(
    pool: asyncpg.Pool, *, username: str, password: str, dob: str | None, role: str, profile_id: str | None
) -> dict:
    async with pool.acquire() as conn:
        existing = await conn.fetchrow("SELECT id FROM users WHERE username = $1", username)
        if existing:
            raise ServiceError(409, "Username already taken")

        user_id = str(uuid4())
        now = datetime.now(timezone.utc)
        hashed = security.hash_password(password)
        dob_value = date.fromisoformat(dob) if dob else None

        row = await conn.fetchrow(
            """
            INSERT INTO users (id, username, password, dob, profile_id, role, created_at, updated_at)
            VALUES ($1, $2, $3, $4, $5, $6, $7, $7)
            RETURNING id, username, dob, profile_id, role, created_at, updated_at
            """,
            user_id,
            username,
            hashed,
            dob_value,
            profile_id,
            role,
            now,
        )

    user = _sanitize(row)
    token = security.issue_token(user["id"], user["username"], user["role"])
    return {"user": user, "token": token}


async def login(pool: asyncpg.Pool, *, username: str, password: str) -> dict:
    async with pool.acquire() as conn:
        row = await conn.fetchrow("SELECT * FROM users WHERE username = $1", username)

    if not row or not security.verify_password(password, row["password"]):
        raise ServiceError(401, "Invalid credentials")

    user = _sanitize(row)
    token = security.issue_token(user["id"], user["username"], user["role"])
    return {"user": user, "token": token}
