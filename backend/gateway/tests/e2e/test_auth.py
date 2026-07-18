import re
import time
import uuid

import jwt
import pytest

from tests.e2e.conftest import unique_username

ISO_MS_RE = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{3}Z$")


async def test_register_happy_path(client):
    username = unique_username()
    resp = await client.post(
        "/auth/register",
        json={"username": username, "password": "hunter2pass", "dob": "1995-05-20", "role": "founder"},
    )
    assert resp.status_code == 201
    body = resp.json()
    user = body["user"]
    assert user["username"] == username
    assert user["dob"] == "1995-05-20"
    assert user["role"] == "founder"
    assert user["profileId"] is None
    assert "password" not in user
    assert uuid.UUID(user["id"])
    assert ISO_MS_RE.match(user["createdAt"])
    assert ISO_MS_RE.match(user["updatedAt"])
    assert isinstance(body["token"], str) and body["token"]


@pytest.mark.parametrize(
    "payload,expected_error",
    [
        ({"password": "x", "role": "founder"}, "username, password and role are required"),
        ({"username": "x", "role": "founder"}, "username, password and role are required"),
        ({"username": "x", "password": "y"}, "username, password and role are required"),
    ],
)
async def test_register_missing_fields_400(client, payload, expected_error):
    resp = await client.post("/auth/register", json=payload)
    assert resp.status_code == 400
    assert resp.json() == {"error": expected_error}


async def test_register_invalid_role_400(client):
    resp = await client.post(
        "/auth/register",
        json={"username": unique_username(), "password": "hunter2pass", "role": "vc"},
    )
    assert resp.status_code == 400
    assert resp.json() == {"error": "role must be one of: founder, investor"}


async def test_register_admin_role_rejected(client):
    # AC: role=admin must be rejected at the API; admins are provisioned only
    # by a direct DB write (see test_login_admin_provisioned_via_db below).
    resp = await client.post(
        "/auth/register",
        json={"username": unique_username(), "password": "hunter2pass", "role": "admin"},
    )
    assert resp.status_code == 400
    assert resp.json() == {"error": "role must be one of: founder, investor"}


async def test_register_duplicate_username_409(client):
    username = unique_username()
    payload = {"username": username, "password": "hunter2pass", "role": "investor"}
    first = await client.post("/auth/register", json=payload)
    assert first.status_code == 201

    second = await client.post("/auth/register", json=payload)
    assert second.status_code == 409
    assert second.json() == {"error": "Username already taken"}


async def test_login_happy_path(client):
    username = unique_username()
    password = "correct-horse-battery"
    await client.post("/auth/register", json={"username": username, "password": password, "role": "investor"})

    resp = await client.post("/auth/login", json={"username": username, "password": password})
    assert resp.status_code == 200
    body = resp.json()
    assert body["user"]["username"] == username
    assert "password" not in body["user"]
    assert isinstance(body["token"], str) and body["token"]


@pytest.mark.parametrize(
    "payload",
    [
        {"password": "x"},
        {"username": "x"},
        {},
    ],
)
async def test_login_missing_fields_400(client, payload):
    resp = await client.post("/auth/login", json=payload)
    assert resp.status_code == 400
    assert resp.json() == {"error": "username and password are required"}


async def test_login_unknown_user_401(client):
    resp = await client.post("/auth/login", json={"username": unique_username("ghost"), "password": "whatever"})
    assert resp.status_code == 401
    assert resp.json() == {"error": "Invalid credentials"}


async def test_login_wrong_password_401(client):
    username = unique_username()
    await client.post("/auth/register", json={"username": username, "password": "rightpass", "role": "founder"})

    resp = await client.post("/auth/login", json={"username": username, "password": "wrongpass"})
    assert resp.status_code == 401
    assert resp.json() == {"error": "Invalid credentials"}


async def test_login_admin_provisioned_via_db(client, db_conn):
    # Admin users can log in but can never be created through /auth/register
    # (see test_register_admin_role_rejected) -- only by a direct DB write,
    # exactly as production admins are provisioned.
    from app.security import hash_password

    username = unique_username("admin")
    password = "super-secret-admin-pass"
    user_id = str(uuid.uuid4())
    now = time.time()
    from datetime import datetime, timezone

    await db_conn.execute(
        """
        INSERT INTO users (id, username, password, role, created_at, updated_at)
        VALUES ($1, $2, $3, 'admin', $4, $4)
        """,
        user_id,
        username,
        hash_password(password),
        datetime.fromtimestamp(now, tz=timezone.utc),
    )

    resp = await client.post("/auth/login", json={"username": username, "password": password})
    assert resp.status_code == 200
    body = resp.json()
    assert body["user"]["role"] == "admin"
    assert body["user"]["id"] == user_id


async def test_me_happy_path(client):
    username = unique_username()
    register_resp = await client.post(
        "/auth/register", json={"username": username, "password": "hunter2pass", "role": "founder"}
    )
    token = register_resp.json()["token"]
    user_id = register_resp.json()["user"]["id"]

    resp = await client.get("/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 200
    claims = resp.json()["user"]
    assert claims["sub"] == user_id
    assert claims["username"] == username
    assert claims["role"] == "founder"
    assert "iat" in claims and "exp" in claims


async def test_me_missing_header_401(client):
    resp = await client.get("/auth/me")
    assert resp.status_code == 401
    assert resp.json() == {"error": "Missing or invalid Authorization header"}


async def test_me_malformed_header_401(client):
    resp = await client.get("/auth/me", headers={"Authorization": "Token abc123"})
    assert resp.status_code == 401
    assert resp.json() == {"error": "Missing or invalid Authorization header"}


async def test_me_invalid_token_401(client):
    resp = await client.get("/auth/me", headers={"Authorization": "Bearer not-a-real-jwt"})
    assert resp.status_code == 401
    assert resp.json() == {"error": "Invalid or expired token"}


async def test_me_expired_token_401(client):
    import os

    expired = jwt.encode(
        {"sub": str(uuid.uuid4()), "username": "x", "role": "founder", "iat": int(time.time()) - 100, "exp": int(time.time()) - 50},
        os.environ["JWT_SECRET"],
        algorithm="HS256",
    )
    resp = await client.get("/auth/me", headers={"Authorization": f"Bearer {expired}"})
    assert resp.status_code == 401
    assert resp.json() == {"error": "Invalid or expired token"}
