import uuid

import pytest
import pytest_asyncio

from tests.e2e.conftest import delete_profile, seed_profile, vector_literal

E1 = vector_literal({0: 1.0})
E2 = vector_literal({1: 1.0})
E_06_08 = vector_literal({0: 0.6, 1: 0.8})


@pytest_asyncio.fixture
async def scenario(db_conn):
    """One investor (Inv) requesting founder matches against FC1 (best), FC2
    (medium, hand-computed exact score), FC3 (worst / no overlap)."""
    inv_id = str(uuid.uuid4())
    fc1_id = str(uuid.uuid4())
    fc2_id = str(uuid.uuid4())
    fc3_id = str(uuid.uuid4())

    await seed_profile(
        db_conn,
        inv_id,
        "investor",
        {
            "sectors": ["fintech", "saas"],
            "stages": ["seed"],
            "geographies": ["us"],
            "check_size_min_usd": 100000,
            "check_size_max_usd": 1000000,
        },
        E1,
    )
    await seed_profile(
        db_conn,
        fc1_id,
        "founder",
        {
            "industry": ["fintech", "saas"],
            "stage": "seed",
            "target_regions": ["us"],
            "funding_ask_usd": 500000,
        },
        E1,
    )
    await seed_profile(
        db_conn,
        fc2_id,
        "founder",
        {
            "industry": ["fintech", "healthtech"],
            "stage": "seed",
            "target_regions": ["europe"],
            "funding_ask_usd": 500000,
        },
        E_06_08,
    )
    await seed_profile(
        db_conn,
        fc3_id,
        "founder",
        {
            "industry": ["biotech"],
            "stage": "series-b",
            "target_regions": ["asia"],
            "funding_ask_usd": 20000000,
        },
        E2,
    )

    yield {"inv": inv_id, "fc1": fc1_id, "fc2": fc2_id, "fc3": fc3_id}

    for uid in (inv_id, fc1_id, fc2_id, fc3_id):
        await delete_profile(db_conn, uid)


@pytest.mark.asyncio
async def test_404_when_no_extracted_profile(client, db_conn):
    resp = await client.get(f"/matches/investors/{uuid.uuid4()}/founders")
    assert resp.status_code == 404
    assert resp.json() == {"error": "No extracted profile for user; run extraction first"}


@pytest.mark.asyncio
async def test_ranking_order_follows_composite_score(client, scenario):
    resp = await client.get(f"/matches/investors/{scenario['inv']}/founders")
    assert resp.status_code == 200
    body = resp.json()
    assert body["userId"] == scenario["inv"]
    assert body["role"] == "investor"

    ids_in_order = [m["userId"] for m in body["matches"]]
    assert ids_in_order == [scenario["fc1"], scenario["fc2"], scenario["fc3"]]


@pytest.mark.asyncio
async def test_exact_vector_and_attribute_score_math(client, scenario):
    resp = await client.get(f"/matches/investors/{scenario['inv']}/founders")
    body = resp.json()
    fc2_match = next(m for m in body["matches"] if m["userId"] == scenario["fc2"])

    # vectorScore: cosine similarity between (1,0,...) and (0.6,0.8,0,...) is exactly 0.6
    assert fc2_match["vectorScore"] == 0.6
    # attributeScore: 0.4*(1/3) [sector] + 0.3 [stage] + 0 [no region overlap] + 0.1 [funding] = 8/15
    assert fc2_match["attributeScore"] == 0.5333
    # score = round(0.7*0.6 + 0.3*(8/15), 4) = round(0.42 + 0.16, 4) = 0.58
    assert fc2_match["score"] == 0.58


@pytest.mark.asyncio
async def test_reasons_strings(client, scenario):
    resp = await client.get(f"/matches/investors/{scenario['inv']}/founders")
    body = resp.json()

    fc1_match = next(m for m in body["matches"] if m["userId"] == scenario["fc1"])
    assert fc1_match["reasons"] == [
        "sector overlap: fintech, saas",
        "stage match: seed",
        "geography match: us",
        "check size fits funding ask",
    ]

    fc3_match = next(m for m in body["matches"] if m["userId"] == scenario["fc3"])
    assert fc3_match["reasons"] == []
    assert fc3_match["score"] == 0.0


@pytest.mark.asyncio
async def test_sector_filter(client, scenario):
    resp = await client.get(
        f"/matches/investors/{scenario['inv']}/founders", params={"sector": "fintech"}
    )
    ids = {m["userId"] for m in resp.json()["matches"]}
    assert ids == {scenario["fc1"], scenario["fc2"]}


@pytest.mark.asyncio
async def test_stage_filter_exact_match(client, scenario):
    resp = await client.get(
        f"/matches/investors/{scenario['inv']}/founders", params={"stage": "Seed"}
    )
    ids = {m["userId"] for m in resp.json()["matches"]}
    assert ids == {scenario["fc1"], scenario["fc2"]}


@pytest.mark.asyncio
async def test_region_filter(client, scenario):
    resp = await client.get(
        f"/matches/investors/{scenario['inv']}/founders", params={"region": "us"}
    )
    ids = {m["userId"] for m in resp.json()["matches"]}
    assert ids == {scenario["fc1"]}
