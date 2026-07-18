import math
from typing import Any

from app.db import get_pool


def parse_number(value: Any) -> float | None:
    if value is None:
        return None
    digits = "".join(c for c in str(value) if c.isdigit() or c == ".")
    try:
        n = float(digits) if digits else float("nan")
    except ValueError:
        return None
    return n if math.isfinite(n) and n > 0 else None


async def load_user_profile(user_id: str) -> dict | None:
    pool = get_pool()
    row = await pool.fetchrow(
        """SELECT u.id AS user_id, u.role, p.*
           FROM users u
           JOIN profiles p ON p.id = u.profile_id
           WHERE u.id = $1""",
        user_id,
    )
    return dict(row) if row else None


def to_list(value: Any) -> list[str]:
    if not value:
        return []
    return [s.strip() for s in str(value).lower().split(",") if s.strip()]


def norm_stage(value: Any) -> str | None:
    return str(value).lower().replace("_", "-") if value else None


def map_profile_to_attributes(row: dict) -> dict:
    regions = to_list(row.get("target_region") or row.get("where_you_operate"))

    if row.get("role") == "investor":
        stage = norm_stage(row.get("stage"))
        return {
            "firm_name": row.get("company_name") or None,
            "investor_type": None,
            "thesis": row.get("description_product") or None,
            "sectors": to_list(row.get("industry")),
            "stages": [stage] if stage else [],
            "geographies": regions,
            "check_size_min_usd": None,
            "check_size_max_usd": parse_number(row.get("avg_initial_investment")),
            "portfolio_highlights": [],
            "constraints": None,
        }

    arr = row.get("arr")
    return {
        "company_name": row.get("company_name") or None,
        "industry": to_list(row.get("industry")),
        "stage": norm_stage(row.get("stage")),
        "country": row.get("country") or None,
        "target_regions": regions,
        "team_size": row.get("num_of_employees"),
        "arr_usd": float(arr) if arr is not None else None,
        "funding_ask_usd": parse_number(row.get("checks")),
        "business_model": None,
        "product_description": row.get("description_product") or None,
        "traction_summary": None,
    }
