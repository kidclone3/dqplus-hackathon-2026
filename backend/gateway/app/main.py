from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app import config, db
from app.errors import ServiceError
from app.routers import auth, matches, profiles

DEFAULT_CORS_REGEX = r"^https?://(dqplus\.ddns\.net|localhost|127\.0\.0\.1)(:\d+)?$"


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    app.state.pool = await db.create_pool()
    await db.bootstrap_schema(app.state.pool)
    yield
    await app.state.pool.close()


app = FastAPI(title="Gateway API", docs_url="/docs", lifespan=lifespan)

if config.CORS_ORIGIN:
    cors_kwargs = {"allow_origins": config.CORS_ORIGIN.split(",")}
else:
    cors_kwargs = {"allow_origin_regex": DEFAULT_CORS_REGEX}

app.add_middleware(
    CORSMiddleware,
    allow_methods=["*"],
    allow_headers=["*"],
    **cors_kwargs,
)


@app.exception_handler(ServiceError)
async def service_error_handler(request: Request, exc: ServiceError) -> JSONResponse:
    return JSONResponse(status_code=exc.status_code, content={"error": exc.message})


@app.exception_handler(StarletteHTTPException)
async def http_exception_handler(request: Request, exc: StarletteHTTPException) -> JSONResponse:
    # Unmatched routes and wrong methods both fall through to the same
    # catch-all 404 in the Express app this mirrors.
    if exc.status_code in (404, 405):
        return JSONResponse(status_code=404, content={"error": "Not found"})
    detail = exc.detail if isinstance(exc.detail, str) else "Error"
    return JSONResponse(status_code=exc.status_code, content={"error": detail})


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    return JSONResponse(status_code=500, content={"error": str(exc) or "Internal server error"})


@app.get("/health")
async def health(request: Request) -> Any:
    try:
        async with request.app.state.pool.acquire() as conn:
            await conn.fetchval("SELECT 1")
        return {"status": "ok", "db": "connected"}
    except Exception:
        return JSONResponse(status_code=503, content={"status": "degraded", "db": "unavailable"})


app.include_router(auth.router)
app.include_router(profiles.router)
app.include_router(matches.router)
