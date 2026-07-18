import asyncio

import pytest
import uvicorn
from fastapi import FastAPI
from fastapi.responses import JSONResponse


@pytest.fixture
async def upstream_matching_api():
    """A tiny real FastAPI/uvicorn server on an ephemeral port standing in for
    the Python matching API. This is a service-boundary double, not a mock of
    the DB or an LLM."""
    upstream = FastAPI()

    @upstream.get("/matches")
    async def matches(startup_id: str | None = None):
        return JSONResponse({"received_startup_id": startup_id, "results": []})

    config = uvicorn.Config(upstream, host="127.0.0.1", port=0, log_level="warning")
    server = uvicorn.Server(config)
    task = asyncio.create_task(server.serve())
    while not server.started:
        await asyncio.sleep(0.01)
    port = server.servers[0].sockets[0].getsockname()[1]

    yield f"http://127.0.0.1:{port}"

    server.should_exit = True
    await task


async def test_matches_proxy_passthrough(client, upstream_matching_api, monkeypatch):
    from app import config as app_config

    monkeypatch.setattr(app_config, "MATCHING_API_URL", upstream_matching_api)

    resp = await client.get("/matches?startup_id=abc123")
    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("application/json")
    assert resp.json() == {"received_startup_id": "abc123", "results": []}


async def test_matches_proxy_preserves_query_string_absence(client, upstream_matching_api, monkeypatch):
    from app import config as app_config

    monkeypatch.setattr(app_config, "MATCHING_API_URL", upstream_matching_api)

    resp = await client.get("/matches")
    assert resp.status_code == 200
    assert resp.json() == {"received_startup_id": None, "results": []}


async def test_matches_proxy_upstream_failure_500(client, monkeypatch):
    from app import config as app_config

    # Nothing listens here -> connection refused.
    monkeypatch.setattr(app_config, "MATCHING_API_URL", "http://127.0.0.1:1")

    resp = await client.get("/matches")
    assert resp.status_code == 500
    assert "error" in resp.json()
