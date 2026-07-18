import os


def _number_or_default(value: str | None, default: float | int) -> float | int:
    """Mimics JS `Number(value) || default` (NaN/0/missing all fall back)."""
    if value is None or value == "":
        return default
    try:
        n = float(value)
    except ValueError:
        return default
    return n if n != 0 else default


PORT = int(os.environ.get("PORT") or 3002)

DB_HOST = os.environ.get("DB_HOST", "localhost")
DB_PORT = int(_number_or_default(os.environ.get("DB_PORT"), 5432))
DB_NAME = os.environ.get("DB_NAME", "gateway")
DB_USER = os.environ.get("DB_USER", "postgres")
DB_PASSWORD = os.environ.get("DB_PASSWORD", "")
DB_SSL = os.environ.get("DB_SSL", "false") == "true"

MATCHING_API_URL = os.environ.get("MATCHING_API_URL", "http://localhost:8000")

MATCH_VECTOR_WEIGHT = _number_or_default(os.environ.get("MATCH_VECTOR_WEIGHT"), 0.7)
MATCH_ATTR_WEIGHT = _number_or_default(os.environ.get("MATCH_ATTR_WEIGHT"), 0.3)
MATCH_CANDIDATE_POOL = int(_number_or_default(os.environ.get("MATCH_CANDIDATE_POOL"), 50))
