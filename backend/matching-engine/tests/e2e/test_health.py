import pytest


@pytest.mark.asyncio
async def test_health_ok(client, db_conn):
    resp = await client.get("/health")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok", "db": "connected"}
