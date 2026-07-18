import uuid


async def test_get_extracted_404_when_missing(client):
    resp = await client.get(f"/extracted/{uuid.uuid4()}")
    assert resp.status_code == 404
    assert resp.json() == {"error": "No extracted profile for user"}


async def test_get_extracted_200_after_profile_extraction(client, seeded_founder):
    user_id = seeded_founder
    create = await client.post("/extract/profile", json={"userId": user_id})
    assert create.status_code == 201

    resp = await client.get(f"/extracted/{user_id}")
    assert resp.status_code == 200
    body = resp.json()
    assert body["user_id"] == user_id
    assert body["role"] == "founder"
    assert body["source"] == "profile"
    assert body["attributes"]["company_name"] == "Acme AI"
