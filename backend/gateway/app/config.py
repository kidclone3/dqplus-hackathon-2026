import os


def _env(name: str, default: str | None = None) -> str | None:
    return os.environ.get(name, default)


PORT = int(_env("PORT", "3000"))
HOST = _env("HOST", "0.0.0.0")

CORS_ORIGIN = _env("CORS_ORIGIN")

DB_HOST = _env("DB_HOST", "localhost")
DB_PORT = int(_env("DB_PORT", "5432"))
DB_NAME = _env("DB_NAME", "gateway")
DB_USER = _env("DB_USER", "postgres")
DB_PASSWORD = _env("DB_PASSWORD", "")
DB_SSL = _env("DB_SSL", "false") == "true"

JWT_SECRET = _env("JWT_SECRET")
JWT_EXPIRES_IN = _env("JWT_EXPIRES_IN", "1d")

EXTRACT_SERVICE_URL = _env("EXTRACT_SERVICE_URL")
MATCHING_API_URL = _env("MATCHING_API_URL", "http://localhost:8000")
