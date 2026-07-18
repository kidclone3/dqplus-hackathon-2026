import re
import time
import uuid

import jwt

from tests.e2e.conftest import unique_username

ISO_MS_RE = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{3}Z$")


async def _register(client, role="founder"):
    resp = await client.post(
        "/auth/register",
        json={"username": unique_username(), "password": "hunter2pass", "role": role},
    )
    body = resp.json()
    return body["token"], body["user"]["id"]


async def test_profiles_require_auth(client):
    resp = await client.post("/profiles", json={"company_name": "Acme"})
    assert resp.status_code == 401
    assert resp.json() == {"error": "Missing or invalid Authorization header"}

    resp = await client.get(f"/profiles/{uuid.uuid4()}")
    assert resp.status_code == 401

    resp = await client.patch(f"/profiles/{uuid.uuid4()}", json={})
    assert resp.status_code == 401


async def test_create_profile_happy_path_and_links_user(client, db_conn):
    token, user_id = await _register(client)

    resp = await client.post(
        "/profiles",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "company_name": "Acme Inc",
            "country": "VN",
            "arr": 1000,
            "avg_holding_period": 2.5,
            "website": ["https://acme.example"],
        },
    )
    assert resp.status_code == 201
    profile = resp.json()
    assert profile["company_name"] == "Acme Inc"
    assert profile["country"] == "VN"
    assert profile["arr"] == "1000.00"
    assert profile["avg_holding_period"] == "2.50"
    assert profile["website"] == ["https://acme.example"]
    assert uuid.UUID(profile["id"])
    assert ISO_MS_RE.match(profile["createdAt"])
    assert ISO_MS_RE.match(profile["updatedAt"])

    row = await db_conn.fetchrow("SELECT profile_id FROM users WHERE id = $1", uuid.UUID(user_id))
    assert str(row["profile_id"]) == profile["id"]


async def test_create_profile_missing_company_name_400(client):
    token, _ = await _register(client)
    resp = await client.post("/profiles", headers={"Authorization": f"Bearer {token}"}, json={})
    assert resp.status_code == 400
    assert resp.json() == {"error": "company_name is required"}


async def test_create_profile_user_not_found_404(client):
    # A JWT with a well-formed but non-existent user id.
    import os

    now = int(time.time())
    token = jwt.encode(
        {"sub": str(uuid.uuid4()), "username": "ghost", "role": "founder", "iat": now, "exp": now + 3600},
        os.environ["JWT_SECRET"],
        algorithm="HS256",
    )
    resp = await client.post("/profiles", headers={"Authorization": f"Bearer {token}"}, json={"company_name": "X"})
    assert resp.status_code == 404
    assert resp.json() == {"error": "User not found"}


async def test_create_profile_already_has_profile_409(client):
    token, _ = await _register(client)
    first = await client.post("/profiles", headers={"Authorization": f"Bearer {token}"}, json={"company_name": "First Co"})
    assert first.status_code == 201

    second = await client.post("/profiles", headers={"Authorization": f"Bearer {token}"}, json={"company_name": "Second Co"})
    assert second.status_code == 409
    assert second.json() == {"error": "User already has a profile"}


async def test_get_profile_200(client):
    token, _ = await _register(client)
    created = await client.post("/profiles", headers={"Authorization": f"Bearer {token}"}, json={"company_name": "Getter Co"})
    profile_id = created.json()["id"]

    resp = await client.get(f"/profiles/{profile_id}", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 200
    assert resp.json()["id"] == profile_id
    assert resp.json()["company_name"] == "Getter Co"


async def test_get_profile_readable_by_other_users(client):
    # BR1 (get-profile.md): reads have no ownership check — any authenticated
    # user can fetch any profile by id; only PATCH is owner-restricted.
    owner_token, _ = await _register(client)
    created = await client.post(
        "/profiles", headers={"Authorization": f"Bearer {owner_token}"}, json={"company_name": "Open Book Co"}
    )
    profile_id = created.json()["id"]

    other_token, _ = await _register(client, role="investor")
    resp = await client.get(f"/profiles/{profile_id}", headers={"Authorization": f"Bearer {other_token}"})
    assert resp.status_code == 200
    assert resp.json()["id"] == profile_id


async def test_get_profile_404(client):
    token, _ = await _register(client)
    resp = await client.get(f"/profiles/{uuid.uuid4()}", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 404
    assert resp.json() == {"error": "Profile not found"}


async def test_patch_profile_200(client):
    token, _ = await _register(client)
    created = await client.post("/profiles", headers={"Authorization": f"Bearer {token}"}, json={"company_name": "Patchable Co"})
    profile_id = created.json()["id"]
    original_updated_at = created.json()["updatedAt"]

    resp = await client.patch(
        f"/profiles/{profile_id}", headers={"Authorization": f"Bearer {token}"}, json={"country": "US", "arr": 42}
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["country"] == "US"
    assert body["arr"] == "42.00"
    assert body["company_name"] == "Patchable Co"  # untouched field preserved
    assert body["updatedAt"] != original_updated_at


async def test_patch_profile_forbidden_403(client):
    # Second user does not own the first user's profile.
    token_a, _ = await _register(client)
    created = await client.post("/profiles", headers={"Authorization": f"Bearer {token_a}"}, json={"company_name": "Owner Co"})
    profile_id = created.json()["id"]

    token_b, _ = await _register(client)
    resp = await client.patch(f"/profiles/{profile_id}", headers={"Authorization": f"Bearer {token_b}"}, json={"country": "US"})
    assert resp.status_code == 403
    assert resp.json() == {"error": "Forbidden"}


async def test_patch_profile_not_found_404(client, db_conn):
    # The users.profile_id FK is ON DELETE SET NULL, so deleting a profile
    # through normal means always nulls the owner's profile_id first (which
    # would trip the 403 Forbidden branch, not 404). The app exposes no
    # DELETE /profiles endpoint, so to reach the defensive "profile row
    # missing" branch at all we have to delete the row with the cascade
    # trigger disabled, leaving a dangling (but still-matching) profile_id.
    token, _ = await _register(client)
    created = await client.post("/profiles", headers={"Authorization": f"Bearer {token}"}, json={"company_name": "Real Co"})
    profile_id = created.json()["id"]

    await db_conn.execute("ALTER TABLE profiles DISABLE TRIGGER ALL")
    try:
        await db_conn.execute("DELETE FROM profiles WHERE id = $1", uuid.UUID(profile_id))
    finally:
        await db_conn.execute("ALTER TABLE profiles ENABLE TRIGGER ALL")

    resp = await client.patch(f"/profiles/{profile_id}", headers={"Authorization": f"Bearer {token}"}, json={"country": "US"})
    assert resp.status_code == 404
    assert resp.json() == {"error": "Profile not found"}
