import uuid


async def test_extract_profile_founder_maps_attributes(client, db_conn, seeded_founder):
    user_id = seeded_founder

    resp = await client.post("/extract/profile", json={"userId": user_id})
    assert resp.status_code == 201
    body = resp.json()

    assert body["user_id"] == user_id
    assert body["role"] == "founder"
    assert body["source"] == "profile"

    attrs = body["attributes"]
    assert attrs["company_name"] == "Acme AI"
    assert attrs["industry"] == ["fintech", "ai"]  # to_list("Fintech, AI")
    assert attrs["stage"] == "series-a"  # norm_stage("series_a")
    assert attrs["country"] == "Vietnam"
    assert attrs["target_regions"] == ["vietnam", "singapore"]
    assert attrs["team_size"] == 18
    assert attrs["arr_usd"] == 1200000.0
    assert attrs["funding_ask_usd"] == 500.0  # parse_number("500k")
    assert attrs["business_model"] is None
    assert attrs["product_description"] == "AI-powered fraud detection platform"
    assert attrs["traction_summary"] is None

    row = await db_conn.fetchrow(
        "SELECT embedding, embedding_text FROM extracted_profiles WHERE user_id = $1", user_id
    )
    assert row["embedding_text"]
    embedding = _parse_vector(row["embedding"])
    assert any(x != 0 for x in embedding)


async def test_extract_profile_investor_maps_attributes(client, seeded_investor):
    user_id = seeded_investor

    resp = await client.post("/extract/profile", json={"userId": user_id})
    assert resp.status_code == 201
    body = resp.json()

    assert body["role"] == "investor"
    attrs = body["attributes"]
    assert attrs["firm_name"] == "Golden Gate Ventures"
    assert attrs["investor_type"] is None
    assert attrs["thesis"] == "VC firm investing in early-stage startups"
    assert attrs["sectors"] == ["fintech", "saas"]
    assert attrs["stages"] == ["seed"]
    assert attrs["geographies"] == ["southeast asia"]
    assert attrs["check_size_min_usd"] is None
    assert attrs["check_size_max_usd"] == 250000.0
    assert attrs["portfolio_highlights"] == []
    assert attrs["constraints"] is None


async def test_extract_profile_repost_upserts_single_row(client, db_conn, seeded_founder):
    user_id = seeded_founder

    first = await client.post("/extract/profile", json={"userId": user_id})
    assert first.status_code == 201
    first_id = first.json()["id"]
    first_updated_at = first.json()["updated_at"]

    second = await client.post("/extract/profile", json={"userId": user_id})
    assert second.status_code == 201
    second_body = second.json()
    assert second_body["id"] == first_id
    assert second_body["updated_at"] >= first_updated_at

    count = await db_conn.fetchval(
        "SELECT count(*) FROM extracted_profiles WHERE user_id = $1", user_id
    )
    assert count == 1


async def test_extract_profile_missing_user_id_400(client):
    resp = await client.post("/extract/profile", json={})
    assert resp.status_code == 400
    assert resp.json() == {"error": "userId is required"}


async def test_extract_profile_no_profile_404(client):
    resp = await client.post("/extract/profile", json={"userId": str(uuid.uuid4())})
    assert resp.status_code == 404
    assert resp.json() == {"error": "User has no profile"}


def _parse_vector(text: str) -> list[float]:
    return [float(x) for x in text.strip("[]").split(",")]
