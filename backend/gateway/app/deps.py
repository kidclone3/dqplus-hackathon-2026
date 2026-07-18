import jwt
from fastapi import HTTPException, Request

from app import security


async def read_json_body(request: Request) -> dict:
    """Reads the request body as a dict, tolerating an empty/missing body.
    Unknown keys are simply ignored downstream (never validated here)."""
    try:
        body = await request.json()
    except Exception:
        return {}
    return body if isinstance(body, dict) else {}


def get_current_user(request: Request) -> dict:
    header = request.headers.get("authorization", "")
    scheme, _, token = header.partition(" ")
    if scheme != "Bearer" or not token:
        raise HTTPException(status_code=401, detail="Missing or invalid Authorization header")

    try:
        return security.decode_token(token)
    except jwt.PyJWTError:
        raise HTTPException(status_code=401, detail="Invalid or expired token")
