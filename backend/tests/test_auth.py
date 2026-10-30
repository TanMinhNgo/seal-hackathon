import asyncio
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock

import jwt
import pytest
from pydantic import AnyHttpUrl, SecretStr
from redis.exceptions import ConnectionError as RedisConnectionError
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.core.security import jwt_key, token_hash
from app.main import api
from app.modules.auth import dependencies
from app.modules.auth.dependencies import rate_limit_auth
from app.modules.auth.models import EmailVerificationToken, RefreshSession, User

ACCOUNT = {
    "email": "student@example.com",
    "password": "Strong test password!",
    "full_name": "Student",
}


def register(client, data=None):
    response = client.post("/api/v1/auth/register", json=data or ACCOUNT)
    assert response.status_code == 201
    return response.json()


def verification_token(queue):
    body = queue.call_args.kwargs["args"][2]
    return body.split("?token=")[1].splitlines()[0]


def sign_in(client, queue):
    register(client)
    response = client.post("/api/v1/auth/verify-email", json={"token": verification_token(queue)})
    assert response.status_code == 204 and response.content == b""
    response = client.post(
        "/api/v1/auth/login", json={key: ACCOUNT[key] for key in ("email", "password")}
    )
    assert response.status_code == 200
    return response.json()["access_token"]


def database_query(engine, statement):
    async def execute():
        async with async_sessionmaker(engine, expire_on_commit=False)() as session:
            result = await session.execute(statement)
            rows = result.scalars().all() if statement.is_select else []
            await session.commit()
            return rows

    return asyncio.run(execute())


def test_register_hashes_secrets_and_normalizes_email(auth_client, email_queue, auth_engine):
    user = register(
        auth_client, {**ACCOUNT, "email": "Student@EXAMPLE.COM", "full_name": " Student "}
    )
    assert user["email"] == "student@example.com" and user["full_name"] == "Student"
    assert not user["email_verified"] and not user["is_admin"] and user["is_active"]
    assert user["created_at"].endswith("Z")
    assert "password_hash" not in user and "password" not in user and "token" not in user
    stored_hash = database_query(auth_engine, select(User.password_hash))[0]
    assert stored_hash.startswith("$argon2id$") and stored_hash != ACCOUNT["password"]
    raw_token = verification_token(email_queue)
    assert database_query(auth_engine, select(EmailVerificationToken.token_hash)) == [
        token_hash(raw_token)
    ]
    assert email_queue.call_args.kwargs["args"][0] == ACCOUNT["email"]


def test_duplicate_email_is_case_insensitive(auth_client):
    register(auth_client)
    response = auth_client.post(
        "/api/v1/auth/register", json={**ACCOUNT, "email": "STUDENT@example.com"}
    )
    assert response.status_code == 409 and response.json()["code"] == "EMAIL_TAKEN"


def test_simultaneous_registration_only_creates_one_account(auth_client, email_queue):
    def submit(_):
        return auth_client.post("/api/v1/auth/register", json=ACCOUNT).status_code

    with ThreadPoolExecutor(max_workers=2) as executor:
        statuses = list(executor.map(submit, range(2)))
    assert sorted(statuses) == [201, 409]
    assert email_queue.call_count == 1


def test_simultaneous_refresh_only_accepts_one_request(auth_client, email_queue):
    sign_in(auth_client, email_queue)
    token = auth_client.cookies.get("refresh_token")

    def submit(_):
        return auth_client.post(
            "/api/v1/auth/refresh", headers={"Cookie": f"refresh_token={token}"}
        ).status_code

    with ThreadPoolExecutor(max_workers=2) as executor:
        statuses = list(executor.map(submit, range(2)))
    assert sorted(statuses) == [200, 401]


@pytest.mark.parametrize(
    "changes",
    [
        {"password": "short"},
        {"password": "x" * 129},
        {"email": "invalid"},
        {"full_name": "  "},
        {"is_admin": True},
    ],
)
def test_registration_validation(auth_client, email_queue, changes):
    response = auth_client.post("/api/v1/auth/register", json={**ACCOUNT, **changes})
    assert response.status_code == 422 and response.json()["code"] == "VALIDATION_ERROR"
    email_queue.assert_not_called()


def test_unverified_account_and_wrong_credentials(auth_client):
    register(auth_client)
    response = auth_client.post(
        "/api/v1/auth/login", json={"email": ACCOUNT["email"], "password": "wrong"}
    )
    assert response.status_code == 401 and response.json()["code"] == "INVALID_CREDENTIALS"
    response = auth_client.post(
        "/api/v1/auth/login", json={"email": "missing@example.com", "password": "wrong"}
    )
    assert response.status_code == 401 and response.json()["code"] == "INVALID_CREDENTIALS"
    response = auth_client.post(
        "/api/v1/auth/login", json={key: ACCOUNT[key] for key in ("email", "password")}
    )
    assert response.status_code == 403 and response.json()["code"] == "EMAIL_NOT_VERIFIED"


def test_verification_is_single_use_and_expires(auth_client, email_queue, auth_engine):
    register(auth_client)
    token = verification_token(email_queue)
    database_query(
        auth_engine,
        update(EmailVerificationToken).values(expires_at=datetime.now(UTC) - timedelta(seconds=1)),
    )
    response = auth_client.post("/api/v1/auth/verify-email", json={"token": token})
    assert response.status_code == 400 and response.json()["code"] == "INVALID_TOKEN"
    database_query(
        auth_engine,
        update(EmailVerificationToken).values(expires_at=datetime.now(UTC) + timedelta(hours=1)),
    )
    assert auth_client.post("/api/v1/auth/verify-email", json={"token": token}).status_code == 204
    assert auth_client.post("/api/v1/auth/verify-email", json={"token": token}).status_code == 400


def test_login_cookie_profile_refresh_and_logout(auth_client, email_queue, auth_engine):
    access = sign_in(auth_client, email_queue)
    refresh = auth_client.cookies.get("refresh_token")
    claims = jwt.decode(access, options={"verify_signature": False})
    assert claims["exp"] - claims["iat"] == 900
    cookie = next(iter(auth_client.cookies.jar))
    assert cookie.path == "/api/v1/auth" and cookie.has_nonstandard_attr("HttpOnly")
    assert cookie.get_nonstandard_attr("SameSite") == "lax"
    assert database_query(auth_engine, select(RefreshSession.token_hash)) == [token_hash(refresh)]
    headers = {"Authorization": f"Bearer {access}"}
    response = auth_client.get("/api/v1/users/me", headers=headers)
    assert response.status_code == 200 and response.json()["email"] == ACCOUNT["email"]
    response = auth_client.patch(
        "/api/v1/users/me",
        headers=headers,
        json={
            "full_name": "New name",
            "phone": "0123456789",
            "avatar_url": "https://example.com/avatar.png",
        },
    )
    assert response.status_code == 200 and response.json()["full_name"] == "New name"
    assert (
        auth_client.patch("/api/v1/users/me", headers=headers, json={"phone": None}).json()["phone"]
        is None
    )
    assert auth_client.post("/api/v1/auth/refresh").status_code == 200
    rotated = auth_client.cookies.get("refresh_token")
    assert rotated != refresh
    auth_client.cookies.clear()
    auth_client.cookies.set("refresh_token", refresh, path="/api/v1/auth")
    assert auth_client.post("/api/v1/auth/refresh").status_code == 401
    auth_client.cookies.clear()
    auth_client.cookies.set("refresh_token", rotated, path="/api/v1/auth")
    assert auth_client.post("/api/v1/auth/logout").status_code == 204
    assert auth_client.get("/api/v1/users/me", headers=headers).status_code == 401
    assert auth_client.post("/api/v1/auth/refresh").status_code == 401
    assert auth_client.post("/api/v1/auth/logout").status_code == 204


@pytest.mark.parametrize(
    "body",
    [
        {"is_admin": True},
        {"email_verified": True},
        {"email": "other@example.com"},
        {"full_name": None},
        {"avatar_url": "javascript:alert(1)"},
    ],
)
def test_profile_rejects_privilege_changes_and_invalid_fields(auth_client, email_queue, body):
    access = sign_in(auth_client, email_queue)
    response = auth_client.patch(
        "/api/v1/users/me", headers={"Authorization": f"Bearer {access}"}, json=body
    )
    assert response.status_code == 422


def test_access_and_refresh_types_cannot_be_interchanged(auth_client, email_queue):
    access = sign_in(auth_client, email_queue)
    refresh = auth_client.cookies.get("refresh_token")
    assert (
        auth_client.get(
            "/api/v1/users/me", headers={"Authorization": f"Bearer {refresh}"}
        ).status_code
        == 401
    )
    auth_client.cookies.clear()
    auth_client.cookies.set("refresh_token", access, path="/api/v1/auth")
    assert auth_client.post("/api/v1/auth/refresh").status_code == 401
    assert auth_client.get("/api/v1/users/me").status_code == 401


def test_expired_and_tampered_access_token(auth_client, email_queue, auth_settings):
    access = sign_in(auth_client, email_queue)
    claims = jwt.decode(access, options={"verify_signature": False})
    claims["exp"] = int((datetime.now(UTC) - timedelta(seconds=1)).timestamp())
    expired = jwt.encode(claims, jwt_key(auth_settings), algorithm="HS256")
    for token in (expired, access + "tampered", "not-a-jwt"):
        response = auth_client.get("/api/v1/users/me", headers={"Authorization": f"Bearer {token}"})
        assert response.status_code == 401 and response.json()["code"] == "INVALID_TOKEN"

    claims["exp"] = int((datetime.now(UTC) + timedelta(minutes=5)).timestamp())
    claims["sid"] = 123
    invalid_claim = jwt.encode(claims, jwt_key(auth_settings), algorithm="HS256")
    response = auth_client.get(
        "/api/v1/users/me", headers={"Authorization": f"Bearer {invalid_claim}"}
    )
    assert response.status_code == 401


def test_expired_server_session_blocks_access(auth_client, email_queue, auth_engine):
    access = sign_in(auth_client, email_queue)
    database_query(
        auth_engine,
        update(RefreshSession).values(expires_at=datetime.now(UTC) - timedelta(seconds=1)),
    )
    assert (
        auth_client.get(
            "/api/v1/users/me", headers={"Authorization": f"Bearer {access}"}
        ).status_code
        == 401
    )


def test_weak_jwt_secret_fails_closed(auth_client, email_queue, auth_settings):
    access = sign_in(auth_client, email_queue)
    auth_settings.jwt_secret = SecretStr("weak")
    response = auth_client.get("/api/v1/users/me", headers={"Authorization": f"Bearer {access}"})
    assert response.status_code == 503 and response.json()["code"] == "AUTH_NOT_CONFIGURED"


def test_https_frontend_enables_secure_cookie(auth_client, email_queue, auth_settings):
    auth_settings.frontend_url = AnyHttpUrl("https://seal.example")
    sign_in(auth_client, email_queue)
    cookie = next(iter(auth_client.cookies.jar))
    assert cookie.secure and cookie.has_nonstandard_attr("HttpOnly")


def test_disabled_account_is_rejected_immediately(auth_client, email_queue, auth_engine):
    access = sign_in(auth_client, email_queue)
    database_query(auth_engine, update(User).values(is_active=False))
    assert (
        auth_client.get("/api/v1/users/me", headers={"Authorization": f"Bearer {access}"}).json()[
            "code"
        ]
        == "ACCOUNT_DISABLED"
    )
    assert auth_client.post("/api/v1/auth/refresh").status_code == 403
    assert (
        auth_client.post(
            "/api/v1/auth/login", json={key: ACCOUNT[key] for key in ("email", "password")}
        ).status_code
        == 403
    )


def test_resend_is_private_throttled_and_replaces_old_token(auth_client, email_queue, auth_engine):
    register(auth_client)
    old = verification_token(email_queue)
    assert (
        auth_client.post(
            "/api/v1/auth/resend-verification", json={"email": "missing@example.com"}
        ).status_code
        == 204
    )
    assert (
        auth_client.post(
            "/api/v1/auth/resend-verification", json={"email": ACCOUNT["email"]}
        ).status_code
        == 204
    )
    assert email_queue.call_count == 1
    database_query(
        auth_engine,
        update(EmailVerificationToken).values(created_at=datetime.now(UTC) - timedelta(minutes=2)),
    )
    assert (
        auth_client.post(
            "/api/v1/auth/resend-verification", json={"email": ACCOUNT["email"]}
        ).status_code
        == 204
    )
    assert email_queue.call_count == 2
    assert auth_client.post("/api/v1/auth/verify-email", json={"token": old}).status_code == 400
    assert (
        auth_client.post(
            "/api/v1/auth/verify-email", json={"token": verification_token(email_queue)}
        ).status_code
        == 204
    )


def test_queue_failure_keeps_account_for_resend(auth_client, email_queue, auth_engine):
    email_queue.side_effect = RuntimeError("broker unavailable")
    response = auth_client.post("/api/v1/auth/register", json=ACCOUNT)
    assert response.status_code == 503 and response.json()["code"] == "EMAIL_QUEUE_UNAVAILABLE"
    assert database_query(auth_engine, select(User.email)) == [ACCOUNT["email"]]


def test_cookie_origin_check(auth_client, email_queue):
    response = auth_client.post(
        "/api/v1/auth/register", json=ACCOUNT, headers={"Origin": "https://evil.example"}
    )
    assert response.status_code == 403 and response.json()["code"] == "UNTRUSTED_ORIGIN"
    email_queue.assert_not_called()


@pytest.mark.parametrize(
    "outcome, expected", [(31, "RATE_LIMITED"), (RedisConnectionError(), "RATE_LIMIT_UNAVAILABLE")]
)
def test_rate_limit_and_redis_failure(auth_client, monkeypatch, outcome, expected):
    api.dependency_overrides.pop(rate_limit_auth)
    connection = AsyncMock()
    if isinstance(outcome, Exception):
        connection.eval.side_effect = outcome
    else:
        connection.eval.return_value = outcome
    manager = MagicMock()
    manager.__aenter__ = AsyncMock(return_value=connection)
    manager.__aexit__ = AsyncMock(return_value=False)
    monkeypatch.setattr(dependencies.Redis, "from_url", lambda *args, **kwargs: manager)
    response = auth_client.post(
        "/api/v1/auth/login", json={"email": ACCOUNT["email"], "password": "test"}
    )
    assert response.status_code in (429, 503) and response.json()["code"] == expected
