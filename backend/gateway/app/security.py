import re
import time

import bcrypt
import jwt

from app import config

BCRYPT_ROUNDS = 10

_DURATION_RE = re.compile(r"^(\d+(?:\.\d+)?)(s|m|h|d)$")
_DURATION_MULTIPLIERS = {"s": 1, "m": 60, "h": 3600, "d": 86400}


def hash_password(password: str) -> str:
    salt = bcrypt.gensalt(rounds=BCRYPT_ROUNDS)
    return bcrypt.hashpw(password.encode("utf-8"), salt).decode("utf-8")


def verify_password(password: str, hashed: str) -> bool:
    return bcrypt.checkpw(password.encode("utf-8"), hashed.encode("utf-8"))


def _parse_expires_in_seconds(value: str) -> int:
    """Mirrors jsonwebtoken's expiresIn parsing: a bare number is seconds,
    otherwise "<num><s|m|h|d>"."""
    if value.isdigit():
        return int(value)
    match = _DURATION_RE.match(value.strip())
    if not match:
        return 86400  # fall back to 1d
    amount, unit = match.groups()
    return int(float(amount) * _DURATION_MULTIPLIERS[unit])


def issue_token(user_id: str, username: str, role: str) -> str:
    now = int(time.time())
    expires_in = _parse_expires_in_seconds(config.JWT_EXPIRES_IN)
    payload = {
        "sub": user_id,
        "username": username,
        "role": role,
        "iat": now,
        "exp": now + expires_in,
    }
    return jwt.encode(payload, config.JWT_SECRET, algorithm="HS256")


def decode_token(token: str) -> dict:
    return jwt.decode(token, config.JWT_SECRET, algorithms=["HS256"])
