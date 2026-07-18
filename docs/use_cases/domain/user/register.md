# DUC-USER-REGISTER — Register a User

> **Type:** Domain Use Case (DUC)
> **Service:** Gateway (FastAPI port), port 3000
> **Endpoint:** `POST /auth/register`
> **Source of truth:** `backend/gateway/src/routes/auth.routes.js`,
> `backend/gateway/src/services/auth.service.js`, `backend/gateway/src/models/user.model.js`
> **Realizes:** [BUC-MATCHING](../../business/startup-investor-matching.md),
> [BUC-ADMIN](../../business/admin-dashboard-access.md) (negative rule: no admin via API)

## 1. Description

Creates a new user account with role `founder` or `investor`, hashes the password with
bcrypt, and returns the sanitized user plus a signed JWT.

## 2. Actors

- **Anonymous visitor** (no token required).
- **Gateway service**, **Postgres** (`users`).

## 3. Preconditions

- Database reachable; `JWT_SECRET` configured.
- Username not already taken.

## 4. Request

`POST /auth/register`, `Content-Type: application/json`. No authentication.

| Field | Type | Required | Notes |
|-------|------|----------|-------|
| `username` | string | yes | Unique. |
| `password` | string | yes | Hashed with bcrypt (10 salt rounds) before storage. |
| `role` | string | yes | Must be `founder` or `investor`. |
| `dob` | string (date) | no | Optional date of birth. |
| `profileId` | string (uuid) | no | Optional pre-existing profile link. |

## 5. Main Flow

```mermaid
flowchart TD
    A[POST /auth/register] --> B{username, password, role present?}
    B -- no --> E1[400 fields required]
    B -- yes --> C{role in founder|investor?}
    C -- no --> E2[400 role must be one of]
    C -- yes --> D{username already exists?}
    D -- yes --> E3[409 Username already taken]
    D -- no --> F[bcrypt-hash password, INSERT user]
    F --> G[sign JWT sub/username/role]
    G --> H[201 user + token]
```

1. Validate that `username`, `password`, and `role` are all present.
2. Validate that `role ∈ {founder, investor}`.
3. Reject if a user with that `username` already exists.
4. Create the user; the `beforeCreate` hook bcrypt-hashes the password (10 rounds).
5. Issue a JWT: payload `{ sub: user.id, username, role }`, HS256, `expiresIn` = `JWT_EXPIRES_IN`
   (default `1d`).
6. Return `201` with the sanitized user (password field removed) and the token.

**Success response — 201:**
```json
{ "user": { "id": "<uuid>", "username": "...", "role": "founder", "dob": null,
            "profileId": null, "createdAt": "...", "updatedAt": "..." },
  "token": "<jwt>" }
```

## 6. Alternative Flows

- **AF1 — With `profileId`/`dob`:** Optional fields are persisted as provided; behavior is
  otherwise identical.

## 7. Exception Flows

- **EF1** Missing `username`, `password`, or `role` → `400 {"error": "username, password and role are required"}`.
- **EF2** `role` not in `founder|investor` (including `role=admin`) → `400 {"error": "role must be one of: founder, investor"}`.
- **EF3** Username already taken → `409 {"error": "Username already taken"}`.

## 8. Business Rules

- **BR1** Passwords are stored only as bcrypt hashes (10 salt rounds); the plaintext is never
  persisted or returned.
- **BR2** The response never includes the `password` field (default scope excludes it; the
  service also strips it).
- **BR3** The JWT is HS256, signed with `JWT_SECRET`, and carries `sub`, `username`, `role`,
  plus standard `iat`/`exp`; it expires per `JWT_EXPIRES_IN` (default `1d`).
- **BR4** `role` is restricted to `founder|investor` at the API. **`admin` can never be created
  through this endpoint** — admin is provisioned only by direct database update
  (see [BUC-ADMIN](../../business/admin-dashboard-access.md) BR1).
- **BR5** `username` is unique.

## 9. Acceptance Criteria

- **AC1** Valid founder/investor registration returns `201` with a user (no `password`) and a
  verifiable JWT whose `role` matches the request.
- **AC2** Missing any of `username`/`password`/`role` returns EF1's exact 400 payload.
- **AC3** `role` outside `founder|investor` returns EF2's exact 400 payload.
- **AC4** `role=admin` is rejected with EF2's 400 payload (no account created).
- **AC5** Registering an existing username returns EF3's exact 409 payload.
- **AC6** The stored password verifies against the plaintext via bcrypt (hash round-trip).

## 10. Cross-References

- Next step: [Create profile](../profile/create-profile.md).
- Token consumers: [Get current user](get-current-user.md), [Login](login.md).
- Admin negative rule: [BUC-ADMIN](../../business/admin-dashboard-access.md).
