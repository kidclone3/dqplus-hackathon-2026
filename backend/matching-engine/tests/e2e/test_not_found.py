import pytest


@pytest.mark.asyncio
async def test_unknown_route_returns_json_404(client, db_conn):
    resp = await client.get("/this-route-does-not-exist")
    assert resp.status_code == 404
    assert resp.json() == {"error": "Not found"}
