import uuid

import pytest
import pytest_asyncio

from tests.e2e.conftest import delete_profile, seed_profile, vector_literal

E1 = vector_literal({0: 1.0})
E2 = vector_literal({1: 1.0})
E_06_08 = vector_literal({0: 0.6, 1: 0.8})


@pytest_asyncio.fixture
async def scenario(db_conn):
    """One founder (F) requesting investor matches against I1 (best), I2 (medium,
    hand-computed exact score), I3 (worst / no overlap)."""
    f_id = str(uuid.uuid4())
    i1_id = str(uuid.uuid4())
    i2_id = str(uuid.uuid4())
    i3_id = str(uuid.uuid4())

    await seed_profile(
        db_conn,
        f_id,
        "founder",
        {
            "industry": ["fintech", "saas"],
            "stage": "seed",
            "target_regions": ["us", "europe"],
            "funding_ask_usd": 500000,
        },
        E1,
    )
    await seed_profile(
        db_conn,
        i1_id,
        "investor",
        {
            "sectors": ["fintech", "saas"],
            "stages": ["seed"],
            "geographies": ["global"],
            "check_size_min_usd": 100000,
            "check_size_max_usd": 1000000,
        },
        E1,
    )
    await seed_profile(
        db_conn,
        i2_id,
        "investor",
        {
            "sectors": ["fintech", "healthtech"],
            "stages": ["seed", "series-a"],
            "geographies": ["us"],
            "check_size_min_usd": 100000,
            "check_size_max_usd": 1000000,
        },
        E_06_08,
    )
    await seed_profile(
        db_conn,
        i3_id,
        "investor",
        {
            "sectors": ["biotech"],
            "stages": ["series-b"],
            "geographies": ["asia"],
            "check_size_min_usd": 5000000,
            "check_size_max_usd": 10000000,
        },
        E2,
    )

    yield {"f": f_id, "i1": i1_id, "i2": i2_id, "i3": i3_id}

    for uid in (f_id, i1_id, i2_id, i3_id):
        await delete_profile(db_conn, uid)


@pytest.mark.asyncio
async def test_404_when_no_extracted_profile(client, db_conn):
    resp = await client.get(f"/matches/founders/{uuid.uuid4()}/investors")
    assert resp.status_code == 404
    assert resp.json() == {"error": "No extracted profile for user; run extraction first"}


@pytest.mark.asyncio
async def test_ranking_order_follows_composite_score(client, scenario):
    resp = await client.get(f"/matches/founders/{scenario['f']}/investors")
    assert resp.status_code == 200
    body = resp.json()
    assert body["userId"] == scenario["f"]
    assert body["role"] == "founder"

    ids_in_order = [m["userId"] for m in body["matches"]]
    assert ids_in_order == [scenario["i1"], scenario["i2"], scenario["i3"]]

    scores = [m["score"] for m in body["matches"]]
    assert scores == sorted(scores, reverse=True)


@pytest.mark.asyncio
async def test_exact_vector_and_attribute_score_math(client, scenario):
    resp = await client.get(f"/matches/founders/{scenario['f']}/investors")
    body = resp.json()
    i2_match = next(m for m in body["matches"] if m["userId"] == scenario["i2"])

    # vectorScore: cosine similarity between (1,0,...) and (0.6,0.8,0,...) is exactly 0.6
    assert i2_match["vectorScore"] == 0.6
    # attributeScore: 0.4*(1/3) [sector] + 0.3 [stage] + 0.2 [region] + 0.1 [funding] = 11/15
    assert i2_match["attributeScore"] == 0.7333
    # score = round(0.7*0.6 + 0.3*(11/15), 4) = round(0.42 + 0.22, 4) = 0.64
    assert i2_match["score"] == 0.64


@pytest.mark.asyncio
async def test_reasons_strings(client, scenario):
    resp = await client.get(f"/matches/founders/{scenario['f']}/investors")
    body = resp.json()

    i1_match = next(m for m in body["matches"] if m["userId"] == scenario["i1"])
    assert i1_match["reasons"] == [
        "sector overlap: fintech, saas",
        "stage match: seed",
        "investor invests globally",
        "check size fits funding ask",
    ]

    i2_match = next(m for m in body["matches"] if m["userId"] == scenario["i2"])
    assert i2_match["reasons"] == [
        "sector overlap: fintech",
        "stage match: seed",
        "geography match: us",
        "check size fits funding ask",
    ]

    i3_match = next(m for m in body["matches"] if m["userId"] == scenario["i3"])
    assert i3_match["reasons"] == []
    assert i3_match["score"] == 0.0


@pytest.mark.asyncio
async def test_sector_filter_is_case_insensitive(client, scenario):
    resp = await client.get(
        f"/matches/founders/{scenario['f']}/investors", params={"sector": "FinTech"}
    )
    ids = {m["userId"] for m in resp.json()["matches"]}
    assert ids == {scenario["i1"], scenario["i2"]}


@pytest.mark.asyncio
async def test_stage_filter(client, scenario):
    resp = await client.get(
        f"/matches/founders/{scenario['f']}/investors", params={"stage": "seed"}
    )
    ids = {m["userId"] for m in resp.json()["matches"]}
    assert ids == {scenario["i1"], scenario["i2"]}


@pytest.mark.asyncio
async def test_region_filter_is_literal_jsonb_containment(client, scenario):
    # I1's geographies is ["global"] which does NOT literally contain "us" —
    # the "global means everywhere" rule only applies at scoring time, not here.
    resp = await client.get(
        f"/matches/founders/{scenario['f']}/investors", params={"region": "us"}
    )
    ids = {m["userId"] for m in resp.json()["matches"]}
    assert ids == {scenario["i2"]}


@pytest.mark.asyncio
async def test_limit_zero_falls_back_to_default_ten(client, scenario):
    # Node's `Number(value) || 10` treats 0 as falsy, so limit=0 falls back to
    # the default of 10 rather than being clamped by Math.max(n, 1) — that
    # clamp only applies to truthy (nonzero) values, e.g. negative numbers.
    resp = await client.get(
        f"/matches/founders/{scenario['f']}/investors", params={"limit": "0"}
    )
    matches = resp.json()["matches"]
    assert len(matches) == 3  # falls back to default 10, all 3 candidates fit


@pytest.mark.asyncio
async def test_negative_limit_clamps_to_one(client, scenario):
    resp = await client.get(
        f"/matches/founders/{scenario['f']}/investors", params={"limit": "-5"}
    )
    matches = resp.json()["matches"]
    assert len(matches) == 1
    assert matches[0]["userId"] == scenario["i1"]


@pytest.mark.asyncio
async def test_limit_999_clamps_to_50(client, scenario):
    resp = await client.get(
        f"/matches/founders/{scenario['f']}/investors", params={"limit": "999"}
    )
    matches = resp.json()["matches"]
    assert len(matches) == 3  # only 3 candidates exist, well under the 50 cap


@pytest.mark.asyncio
async def test_in_range_limit_truncates_list(client, scenario):
    # Regression: an in-range limit (e.g. 2) must slice the list, not 500.
    # float→slice crashed before parse_limit truncated to int.
    resp = await client.get(
        f"/matches/founders/{scenario['f']}/investors", params={"limit": "2"}
    )
    assert resp.status_code == 200
    assert len(resp.json()["matches"]) == 2


@pytest.mark.asyncio
async def test_default_limit_is_ten(client, scenario):
    resp = await client.get(f"/matches/founders/{scenario['f']}/investors")
    matches = resp.json()["matches"]
    assert len(matches) == 3  # fewer than the default 10, so all returned
