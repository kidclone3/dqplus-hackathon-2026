from datetime import datetime, timezone
from decimal import Decimal


def js_iso(dt: datetime) -> str:
    """Matches JavaScript's Date.prototype.toISOString(): UTC, millisecond
    precision, trailing Z."""
    dt = dt.astimezone(timezone.utc)
    return dt.strftime("%Y-%m-%dT%H:%M:%S.") + f"{dt.microsecond // 1000:03d}Z"


def decimal_str(value: Decimal | None) -> str | None:
    """asyncpg returns numeric columns as decimal.Decimal already rounded to
    the column's declared scale; Sequelize/pg would serialize the same value
    as a plain string."""
    return str(value) if value is not None else None
