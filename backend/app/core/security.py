from datetime import UTC, datetime, timedelta
from hashlib import sha256
from secrets import token_urlsafe
from uuid import UUID

import jwt
from pwdlib import PasswordHash

from app.core.config import Settings
from app.core.errors import ApiError

password_hasher = PasswordHash.recommended()
DUMMY_PASSWORD_HASH = password_hasher.hash(token_urlsafe(32))
ACCESS_TTL = timedelta(minutes=15)
REFRESH_TTL = timedelta(days=7)
VERIFY_TTL = timedelta(hours=24)


def token_hash(token: str) -> str:
    return sha256(token.encode()).hexdigest()


def jwt_key(settings: Settings) -> str:
    value = settings.jwt_secret.get_secret_value() if settings.jwt_secret else ""
    if len(value.encode()) < 32:
        raise ApiError(503, "AUTH_NOT_CONFIGURED", "Authentication is not configured")
    return value


def issue_tokens(settings: Settings, user_id: UUID, session_id: UUID) -> tuple[str, str, datetime]:
    now = datetime.now(UTC)
    expires = now + REFRESH_TTL
    claims = {
        "iss": "seal",
        "aud": "seal-api",
        "sub": str(user_id),
        "sid": str(session_id),
        "iat": now,
    }
    access = jwt.encode(
        {**claims, "jti": token_urlsafe(16), "token_type": "access", "exp": now + ACCESS_TTL},
        jwt_key(settings),
        algorithm="HS256",
    )
    refresh = jwt.encode(
        {**claims, "jti": token_urlsafe(16), "token_type": "refresh", "exp": expires},
        jwt_key(settings),
        algorithm="HS256",
    )
    return access, refresh, expires


def decode_token(settings: Settings, token: str, token_type: str) -> tuple[UUID, UUID]:
    try:
        claims = jwt.decode(
            token,
            jwt_key(settings),
            algorithms=["HS256"],
            issuer="seal",
            audience="seal-api",
            options={"require": ["exp", "iat", "iss", "aud", "sub", "sid", "jti", "token_type"]},
        )
        if not all(isinstance(claims[key], str) for key in ("sub", "sid", "jti", "token_type")):
            raise ValueError("Invalid claim type")
        if claims["token_type"] != token_type:
            raise ValueError("Invalid token type")
        return UUID(claims["sub"]), UUID(claims["sid"])
    except (jwt.InvalidTokenError, ValueError, TypeError) as exc:
        raise ApiError(401, "INVALID_TOKEN", "Invalid or expired token") from exc
