import uuid

# Only 400-path coverage here: a successful /extract/crawl call needs a real LLM
# key, which the e2e suite intentionally runs without.


async def test_missing_fields_400(client):
    resp = await client.post(
        "/extract/crawl", json={"userId": str(uuid.uuid4()), "role": "founder", "url": "https://x.com"}
    )
    assert resp.status_code == 400
    assert resp.json() == {"error": "userId, role, url and content are required"}


async def test_missing_all_fields_400(client):
    resp = await client.post("/extract/crawl", json={})
    assert resp.status_code == 400
    assert resp.json() == {"error": "userId, role, url and content are required"}


async def test_bad_role_400(client):
    resp = await client.post(
        "/extract/crawl",
        json={
            "userId": str(uuid.uuid4()),
            "role": "admin",
            "url": "https://x.com",
            "content": "hello",
        },
    )
    assert resp.status_code == 400
    assert resp.json() == {"error": "role must be one of: founder, investor"}
