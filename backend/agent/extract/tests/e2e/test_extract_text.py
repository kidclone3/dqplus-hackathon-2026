import uuid

# Only 400-path coverage here: a successful /extract/text call needs a real LLM
# key (extract_attributes calls the chat completion endpoint), which the e2e
# suite intentionally runs without (OPENAI_API_KEY is forced empty in conftest).


async def test_missing_fields_400(client):
    resp = await client.post("/extract/text", json={"userId": str(uuid.uuid4()), "role": "founder"})
    assert resp.status_code == 400
    assert resp.json() == {"error": "userId, role and text are required"}


async def test_missing_all_fields_400(client):
    resp = await client.post("/extract/text", json={})
    assert resp.status_code == 400
    assert resp.json() == {"error": "userId, role and text are required"}


async def test_bad_role_400(client):
    resp = await client.post(
        "/extract/text", json={"userId": str(uuid.uuid4()), "role": "admin", "text": "hello"}
    )
    assert resp.status_code == 400
    assert resp.json() == {"error": "role must be one of: founder, investor"}
