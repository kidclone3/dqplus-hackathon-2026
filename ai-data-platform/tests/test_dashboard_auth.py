"""Admin gate on the dashboard (GET /) — gateway-issued HS256 JWTs, role=admin.

Covers docs/use_cases/business/admin-dashboard-access.md: 401 without a token,
403 for non-admin/invalid/expired tokens, 200 for an admin bearer token, the
?token= → cookie redirect flow, and the documented fail-open when JWT_SECRET is
unset (standalone dev mode).
"""
import base64
import hashlib
import hmac
import json
import os
import time

import asyncpg
import pytest
from fastapi.testclient import TestClient

from spine import config

SECRET = "dashboard-test-secret"
TEST_DSN = os.environ.get(
    "TEST_DATABASE_URL", "postgres://dealflow:dealflow@localhost:5434/dealflow"
)


def _b64url(b: bytes) -> str:
    return base64.urlsafe_b64encode(b).rstrip(b"=").decode()


def make_token(payload: dict, secret: str = SECRET, alg: str = "HS256") -> str:
    header = _b64url(json.dumps({"alg": alg, "typ": "JWT"}).encode())
    body = _b64url(json.dumps(payload).encode())
    sig = _b64url(hmac.new(secret.encode(), f"{header}.{body}".encode(), hashlib.sha256).digest())
    return f"{header}.{body}.{sig}"


def _claims(role: str, exp_offset: int = 3600) -> dict:
    now = int(time.time())
    return {"sub": "u-test", "username": "t", "role": role, "iat": now, "exp": now + exp_offset}


async def _db_reachable() -> bool:
    try:
        conn = await asyncpg.connect(TEST_DSN, timeout=3)
        await conn.close()
        return True
    except Exception:
        return False


@pytest.fixture(scope="module")
def client():
    import asyncio

    if not asyncio.run(_db_reachable()):
        pytest.skip(f"test Postgres not reachable at {TEST_DSN}")
    original_dsn = config.DATABASE_URL
    config.DATABASE_URL = TEST_DSN
    from api import app as apimod

    original_secret = apimod._JWT_SECRET
    apimod._JWT_SECRET = SECRET
    try:
        with TestClient(apimod.app) as c:
            yield c
    finally:
        apimod._JWT_SECRET = original_secret
        config.DATABASE_URL = original_dsn


def test_dashboard_requires_token(client):
    resp = client.get("/", follow_redirects=False)
    assert resp.status_code == 401


def test_dashboard_rejects_invalid_token(client):
    resp = client.get("/", headers={"Authorization": "Bearer not-a-jwt"})
    assert resp.status_code == 403


def test_dashboard_rejects_non_admin(client):
    resp = client.get("/", headers={"Authorization": f"Bearer {make_token(_claims('founder'))}"})
    assert resp.status_code == 403


def test_dashboard_rejects_expired_admin(client):
    token = make_token(_claims("admin", exp_offset=-60))
    resp = client.get("/", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 403


def test_dashboard_rejects_bad_signature(client):
    token = make_token(_claims("admin"), secret="wrong-secret")
    resp = client.get("/", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 403


def test_dashboard_admin_bearer_ok(client):
    resp = client.get("/", headers={"Authorization": f"Bearer {make_token(_claims('admin'))}"})
    assert resp.status_code == 200
    assert "text/html" in resp.headers["content-type"]


def test_dashboard_query_token_sets_cookie_then_cookie_works(client):
    token = make_token(_claims("admin"))
    redirect = client.get(f"/?token={token}", follow_redirects=False)
    assert redirect.status_code == 303
    assert redirect.headers["location"] == "/"
    assert "vn_admin" in redirect.headers.get("set-cookie", "")

    # TestClient's cookie jar now holds vn_admin — a bare GET / succeeds.
    resp = client.get("/", follow_redirects=False)
    assert resp.status_code == 200
    assert "text/html" in resp.headers["content-type"]


def test_dashboard_query_token_non_admin_rejected(client):
    token = make_token(_claims("investor"))
    resp = client.get(f"/?token={token}", follow_redirects=False)
    assert resp.status_code == 403


def test_dashboard_open_when_secret_unset(client):
    # Documented standalone-dev behavior (README/.env.example): empty
    # JWT_SECRET leaves the dashboard open. Compose always sets a secret.
    from api import app as apimod

    client.cookies.clear()
    prev = apimod._JWT_SECRET
    apimod._JWT_SECRET = ""
    try:
        resp = client.get("/", follow_redirects=False)
        assert resp.status_code == 200
    finally:
        apimod._JWT_SECRET = prev
