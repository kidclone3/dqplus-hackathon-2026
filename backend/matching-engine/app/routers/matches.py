"""Port of src/routes/match.routes.js — keep endpoint behavior identical."""

import httpx
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import Response

from app import config
from app.services.matching import find_matches

router = APIRouter()


def parse_limit(value: str | None) -> int:
    try:
        n = float(value) if value not in (None, "") else 0
    except ValueError:
        n = 0
    if n != n or not n:  # NaN or falsy → default, like JS `Number(value) || 10`
        n = 10
    # int() truncation matches JS Array.prototype.slice's ToIntegerOrInfinity.
    return int(min(max(n, 1), 50))


# Forward bare GET /matches (and its query string) to the Python API. nginx maps /api/matches here
# after stripping /api, so this is what dqplus.ddns.net/api/matches resolves to. The two
# /matches/{role} routes below are unaffected.
@router.get("/matches")
async def proxy_matches(request: Request) -> Response:
    search = f"?{request.url.query}" if request.url.query else ""
    try:
        async with httpx.AsyncClient(timeout=8.0) as client:
            upstream = await client.get(
                f"{config.MATCHING_API_URL}/matches{search}",
                headers={"Accept": "application/json"},
            )
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=500, detail=str(exc) or "Internal server error")

    return Response(
        content=upstream.content,
        status_code=upstream.status_code,
        media_type=upstream.headers.get("content-type", "application/json"),
    )


@router.get("/matches/founders/{user_id}/investors")
async def founders_to_investors(
    user_id: str,
    limit: str | None = None,
    sector: str | None = None,
    stage: str | None = None,
    region: str | None = None,
) -> dict:
    result = await find_matches(
        user_id=user_id,
        target_role="investor",
        limit=parse_limit(limit),
        filters={"sector": sector, "stage": stage, "region": region},
    )
    return result


@router.get("/matches/investors/{user_id}/founders")
async def investors_to_founders(
    user_id: str,
    limit: str | None = None,
    sector: str | None = None,
    stage: str | None = None,
    region: str | None = None,
) -> dict:
    result = await find_matches(
        user_id=user_id,
        target_role="founder",
        limit=parse_limit(limit),
        filters={"sector": sector, "stage": stage, "region": region},
    )
    return result
