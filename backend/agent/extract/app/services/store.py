import json
from datetime import datetime

import asyncpg

from app.db import get_pool

RETURNING_COLUMNS = "id, user_id, role, source, source_url, attributes, embedding_text, created_at, updated_at"


def _vector_literal(embedding: list[float]) -> str:
    return "[" + ",".join(str(x) for x in embedding) + "]"


def _iso(value: datetime) -> str:
    text = value.isoformat()
    return text.replace("+00:00", "Z") if text.endswith("+00:00") else text


def _serialize(row: asyncpg.Record) -> dict:
    record = dict(row)
    attributes = record.get("attributes")
    if isinstance(attributes, str):
        record["attributes"] = json.loads(attributes)
    for key in ("created_at", "updated_at"):
        if isinstance(record.get(key), datetime):
            record[key] = _iso(record[key])
    for key in ("id", "user_id"):
        if key in record and record[key] is not None:
            record[key] = str(record[key])
    return record


async def upsert_extracted_profile(
    *,
    user_id: str,
    role: str,
    source: str,
    source_url: str | None = None,
    raw_input: str | None = None,
    attributes: dict,
    embedding_text: str,
    embedding: list[float],
) -> dict:
    pool = get_pool()
    row = await pool.fetchrow(
        f"""INSERT INTO extracted_profiles
              (user_id, role, source, source_url, raw_input, attributes, embedding_text, embedding)
            VALUES ($1, $2, $3, $4, $5, $6::jsonb, $7, $8::vector)
            ON CONFLICT (user_id) DO UPDATE SET
              role = EXCLUDED.role,
              source = EXCLUDED.source,
              source_url = EXCLUDED.source_url,
              raw_input = EXCLUDED.raw_input,
              attributes = EXCLUDED.attributes,
              embedding_text = EXCLUDED.embedding_text,
              embedding = EXCLUDED.embedding,
              updated_at = now()
            RETURNING {RETURNING_COLUMNS}""",
        user_id,
        role,
        source,
        source_url,
        raw_input,
        json.dumps(attributes),
        embedding_text,
        _vector_literal(embedding),
    )
    return _serialize(row)


async def get_extracted_profile(user_id: str) -> dict | None:
    pool = get_pool()
    row = await pool.fetchrow(
        f"SELECT {RETURNING_COLUMNS} FROM extracted_profiles WHERE user_id = $1",
        user_id,
    )
    return _serialize(row) if row else None
