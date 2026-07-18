# api service image (spec §8, R4). FastAPI read API + dashboard (Phase 3).
FROM python:3.12-slim

COPY --from=ghcr.io/astral-sh/uv:latest /uv /bin/uv

WORKDIR /app
COPY pyproject.toml ./
COPY spine ./spine
COPY spindle ./spindle
COPY apps ./apps
COPY api ./api
COPY dashboard ./dashboard
# schemas/ is read at import time by apps.matchmaker.plugin (R2); kept for the app package's completeness
COPY schemas ./schemas

RUN uv pip install --system asyncpg structlog jsonschema pyyaml fastapi uvicorn

ENV PYTHONUNBUFFERED=1
EXPOSE 8000
CMD ["uvicorn", "api.app:app", "--host", "0.0.0.0", "--port", "8000"]
