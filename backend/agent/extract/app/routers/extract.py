from typing import Any

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from app.services import extraction, embedding, store, profile_source

ROLES = ("founder", "investor")
router = APIRouter()


async def run_pipeline(
    *,
    user_id: str,
    role: str,
    source: str,
    source_url: str | None = None,
    raw_input: str | None = None,
    attributes: dict,
) -> dict:
    embedding_text = extraction.build_embedding_text(role, attributes)
    vector = await embedding.embed(embedding_text)
    return await store.upsert_extracted_profile(
        user_id=user_id,
        role=role,
        source=source,
        source_url=source_url,
        raw_input=raw_input,
        attributes=attributes,
        embedding_text=embedding_text,
        embedding=vector,
    )


@router.post("/extract/text", status_code=201)
async def extract_text(request: Request) -> JSONResponse:
    body = await request.json()
    user_id, role, text = body.get("userId"), body.get("role"), body.get("text")
    if not user_id or not role or not text:
        return JSONResponse(status_code=400, content={"error": "userId, role and text are required"})
    if role not in ROLES:
        return JSONResponse(status_code=400, content={"error": f"role must be one of: {', '.join(ROLES)}"})

    attributes = await extraction.extract_attributes(role, text)
    record = await run_pipeline(user_id=user_id, role=role, source="text", raw_input=text, attributes=attributes)
    return JSONResponse(status_code=201, content=record)


@router.post("/extract/crawl", status_code=201)
async def extract_crawl(request: Request) -> JSONResponse:
    body = await request.json()
    user_id, role, url, content, metadata = (
        body.get("userId"),
        body.get("role"),
        body.get("url"),
        body.get("content"),
        body.get("metadata"),
    )
    if not user_id or not role or not url or not content:
        return JSONResponse(status_code=400, content={"error": "userId, role, url and content are required"})
    if role not in ROLES:
        return JSONResponse(status_code=400, content={"error": f"role must be one of: {', '.join(ROLES)}"})

    extracted = await extraction.extract_attributes(role, content)
    attributes = {**extracted, **metadata} if isinstance(metadata, dict) else extracted
    record = await run_pipeline(
        user_id=user_id, role=role, source="crawler", source_url=url, raw_input=content, attributes=attributes
    )
    return JSONResponse(status_code=201, content=record)


@router.post("/extract/profile", status_code=201)
async def extract_profile(request: Request) -> JSONResponse:
    body = await request.json()
    user_id = body.get("userId")
    if not user_id:
        return JSONResponse(status_code=400, content={"error": "userId is required"})

    row = await profile_source.load_user_profile(user_id)
    if not row:
        return JSONResponse(status_code=404, content={"error": "User has no profile"})

    attributes = profile_source.map_profile_to_attributes(row)
    record = await run_pipeline(user_id=user_id, role=row["role"], source="profile", attributes=attributes)
    return JSONResponse(status_code=201, content=record)


@router.get("/extracted/{user_id}")
async def get_extracted(user_id: str) -> Any:
    record = await store.get_extracted_profile(user_id)
    if not record:
        return JSONResponse(status_code=404, content={"error": "No extracted profile for user"})
    return record
