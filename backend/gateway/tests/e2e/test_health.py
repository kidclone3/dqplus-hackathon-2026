async def test_health_ok(client):
    resp = await client.get("/health")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok", "db": "connected"}


async def test_not_found_unmatched_route(client):
    resp = await client.get("/this-route-does-not-exist")
    assert resp.status_code == 404
    assert resp.json() == {"error": "Not found"}


async def test_not_found_wrong_method(client):
    # PUT isn't registered on /auth/login (only POST) -> falls through to 404,
    # same as the Express app's catch-all (no route matches path+method).
    resp = await client.put("/auth/login")
    assert resp.status_code == 404
    assert resp.json() == {"error": "Not found"}
