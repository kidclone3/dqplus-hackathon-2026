from fastapi import APIRouter, Depends, Request

from app.deps import get_current_user, read_json_body
from app.errors import ServiceError
from app.services import auth_service

ROLES = ["founder", "investor"]

router = APIRouter(prefix="/auth", tags=["Auth"])


@router.post("/register", status_code=201)
async def register(request: Request) -> dict:
    body = await read_json_body(request)
    username = body.get("username")
    password = body.get("password")
    dob = body.get("dob")
    role = body.get("role")
    profile_id = body.get("profileId")

    if not username or not password or not role:
        raise ServiceError(400, "username, password and role are required")
    if role not in ROLES:
        raise ServiceError(400, f"role must be one of: {', '.join(ROLES)}")

    pool = request.app.state.pool
    return await auth_service.register(
        pool, username=username, password=password, dob=dob, role=role, profile_id=profile_id
    )


@router.post("/login")
async def login(request: Request) -> dict:
    body = await read_json_body(request)
    username = body.get("username")
    password = body.get("password")

    if not username or not password:
        raise ServiceError(400, "username and password are required")

    pool = request.app.state.pool
    return await auth_service.login(pool, username=username, password=password)


@router.get("/me")
async def me(current_user: dict = Depends(get_current_user)) -> dict:
    return {"user": current_user}
