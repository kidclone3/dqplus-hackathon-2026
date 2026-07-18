import os


def _int_env(name: str, default: int) -> int:
    value = os.environ.get(name)
    return int(value) if value else default


PORT = _int_env("PORT", 3001)

DB_HOST = os.environ.get("DB_HOST") or "localhost"
DB_PORT = _int_env("DB_PORT", 5432)
DB_NAME = os.environ.get("DB_NAME") or "gateway"
DB_USER = os.environ.get("DB_USER") or "postgres"
DB_PASSWORD = os.environ.get("DB_PASSWORD") or ""
DB_SSL = os.environ.get("DB_SSL") == "true"

OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY") or ""
OPENAI_BASE_URL = os.environ.get("OPENAI_BASE_URL") or "https://mkp-api.fptcloud.com"
OPENAI_CHAT_MODEL = os.environ.get("OPENAI_CHAT_MODEL") or "gpt-4o-mini"
OPENAI_EMBEDDING_MODEL = os.environ.get("OPENAI_EMBEDDING_MODEL") or "text-embedding-3-small"
EMBEDDING_DIM = _int_env("EMBEDDING_DIM", 1536)
