from fastapi import APIRouter, Depends, Request

from app.deps import get_current_user, read_json_body
from app.errors import ServiceError
from app.services import profile_service

router = APIRouter(prefix="/profiles", tags=["Profiles"])


@router.post("", status_code=201)
@router.post("/", status_code=201, include_in_schema=False)
async def create_profile(request: Request, current_user: dict = Depends(get_current_user)) -> dict:
    body = await read_json_body(request)
    if not body.get("company_name"):
        raise ServiceError(400, "company_name is required")

    pool = request.app.state.pool
    return await profile_service.create_profile(pool, current_user["sub"], body)


@router.get("/{profile_id}")
async def get_profile(profile_id: str, request: Request, current_user: dict = Depends(get_current_user)) -> dict:
    pool = request.app.state.pool
    return await profile_service.get_profile(pool, profile_id)


@router.patch("/{profile_id}")
async def update_profile(profile_id: str, request: Request, current_user: dict = Depends(get_current_user)) -> dict:
    body = await read_json_body(request)
    pool = request.app.state.pool
    return await profile_service.update_profile(pool, current_user["sub"], profile_id, body)
