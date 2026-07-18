import httpx
from fastapi import APIRouter, Request, Response

from app import config
from app.errors import ServiceError

router = APIRouter(tags=["Matches"])


@router.get("/matches")
async def get_matches(request: Request) -> Response:
    query = request.scope.get("query_string", b"").decode("utf-8")
    url = f"{config.MATCHING_API_URL}/matches" + (f"?{query}" if query else "")

    try:
        async with httpx.AsyncClient(timeout=8.0) as client:
            upstream = await client.get(url, headers={"Accept": "application/json"})
    except httpx.HTTPError as err:
        raise ServiceError(500, str(err) or "Internal server error")

    return Response(
        content=upstream.content,
        status_code=upstream.status_code,
        media_type=upstream.headers.get("content-type", "application/json"),
    )
