import asyncio
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import pytest
from fastapi import Depends
from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.core.errors import ApiError
from app.core.security import token_hash
from app.main import api
from app.modules.auth.dependencies import require_event_role
from app.modules.auth.models import AuditLog, EventRole, PasswordResetToken, User
from app.modules.auth.repository import AuthRepository
from app.modules.auth.schemas import RegisterInput
from app.modules.auth.service import AuthService
from app.modules.events.models import Event
from tests.test_auth import ACCOUNT, database_query, register, sign_in, verification_token


def admin_headers(client, queue, engine):
    token = sign_in(client, queue)
    database_query(engine, update(User).values(is_admin=True))
    return {"Authorization": f"Bearer {token}"}


def test_forgot_is_private_and_reset_revokes_all_sessions(auth_client, email_queue, auth_engine):
    access = sign_in(auth_client, email_queue)
    refresh = auth_client.cookies.get("refresh_token")
    for email in ("missing@example.com", ACCOUNT["email"]):
        assert (
            auth_client.post("/api/v1/auth/forgot-password", json={"email": email}).status_code
            == 204
        )
    raw = verification_token(email_queue)
    assert "/reset-password?token=" in email_queue.call_args.kwargs["args"][2]
    assert database_query(auth_engine, select(PasswordResetToken.token_hash)) == [token_hash(raw)]
    count = email_queue.call_count
    auth_client.post("/api/v1/auth/forgot-password", json={"email": ACCOUNT["email"]})
    assert email_queue.call_count == count
    response = auth_client.post(
        "/api/v1/auth/reset-password", json={"token": raw, "new_password": "New password 123"}
    )
    assert response.status_code == 204
    assert (
        auth_client.post(
            "/api/v1/auth/reset-password", json={"token": raw, "new_password": "Another password"}
        ).status_code
        == 400
    )
    assert (
        auth_client.get(
            "/api/v1/users/me", headers={"Authorization": f"Bearer {access}"}
        ).status_code
        == 401
    )
    assert (
        auth_client.post(
            "/api/v1/auth/refresh", headers={"Cookie": f"refresh_token={refresh}"}
        ).status_code
        == 401
    )
    assert (
        auth_client.post(
            "/api/v1/auth/login", json={"email": ACCOUNT["email"], "password": ACCOUNT["password"]}
        ).status_code
        == 401
    )
    assert (
        auth_client.post(
            "/api/v1/auth/login", json={"email": ACCOUNT["email"], "password": "New password 123"}
        ).status_code
        == 200
    )


def test_reset_expiry_replacement_and_queue_failure(auth_client, email_queue, auth_engine):
    sign_in(auth_client, email_queue)
    auth_client.post("/api/v1/auth/forgot-password", json={"email": ACCOUNT["email"]})
    old = verification_token(email_queue)
    database_query(
        auth_engine,
        update(PasswordResetToken).values(created_at=datetime.now(UTC) - timedelta(minutes=2)),
    )
    auth_client.post("/api/v1/auth/forgot-password", json={"email": ACCOUNT["email"]})
    new = verification_token(email_queue)
    assert old != new
    assert (
        auth_client.post(
            "/api/v1/auth/reset-password", json={"token": old, "new_password": "New password 123"}
        ).status_code
        == 400
    )
    database_query(
        auth_engine,
        update(PasswordResetToken).values(
            expires_at=datetime.now(UTC) - timedelta(seconds=1),
            created_at=datetime.now(UTC) - timedelta(minutes=2),
        ),
    )
    assert (
        auth_client.post(
            "/api/v1/auth/reset-password", json={"token": new, "new_password": "New password 123"}
        ).status_code
        == 400
    )
    email_queue.side_effect = RuntimeError("do not expose provider details")
    assert (
        auth_client.post(
            "/api/v1/auth/forgot-password", json={"email": ACCOUNT["email"]}
        ).status_code
        == 204
    )


def test_forgot_skips_unverified_and_disabled_accounts(auth_client, email_queue, auth_engine):
    register(auth_client)
    count = email_queue.call_count
    auth_client.post("/api/v1/auth/forgot-password", json={"email": ACCOUNT["email"]})
    database_query(auth_engine, update(User).values(email_verified=True, is_active=False))
    auth_client.post("/api/v1/auth/forgot-password", json={"email": ACCOUNT["email"]})
    assert email_queue.call_count == count


def test_simultaneous_reset_is_single_use(auth_client, email_queue):
    sign_in(auth_client, email_queue)
    auth_client.post("/api/v1/auth/forgot-password", json={"email": ACCOUNT["email"]})
    token = verification_token(email_queue)

    def reset(_):
        return auth_client.post(
            "/api/v1/auth/reset-password", json={"token": token, "new_password": "New password 123"}
        ).status_code

    with ThreadPoolExecutor(max_workers=2) as pool:
        assert sorted(pool.map(reset, range(2))) == [204, 400]


@pytest.mark.parametrize("path", ["/admin/users", "/admin/audit-logs", "/admin/system"])
def test_admin_requires_login_and_admin(auth_client, email_queue, path):
    assert auth_client.get(f"/api/v1{path}").status_code == 401
    access = sign_in(auth_client, email_queue)
    assert (
        auth_client.get(f"/api/v1{path}", headers={"Authorization": f"Bearer {access}"}).status_code
        == 403
    )
    assert (
        auth_client.patch(
            f"/api/v1/admin/users/{uuid4()}",
            headers={"Authorization": f"Bearer {access}"},
            json={"is_admin": True},
        ).status_code
        == 403
    )


def test_admin_updates_audit_filters_and_revokes_disabled_sessions(
    auth_client, email_queue, auth_engine
):
    headers = admin_headers(auth_client, email_queue, auth_engine)
    admin = auth_client.get("/api/v1/users/me", headers=headers).json()
    target = register(auth_client, {**ACCOUNT, "email": "other@example.com", "full_name": "Other"})
    auth_client.post("/api/v1/auth/verify-email", json={"token": verification_token(email_queue)})
    target_access = auth_client.post(
        "/api/v1/auth/login", json={"email": target["email"], "password": ACCOUNT["password"]}
    ).json()["access_token"]
    target_headers = {"Authorization": f"Bearer {target_access}"}
    target_path = f"/api/v1/admin/users/{target['id']}"
    assert (
        auth_client.patch(
            target_path, headers=headers, json={"is_admin": True, "is_active": False}
        ).status_code
        == 200
    )
    assert auth_client.get("/api/v1/users/me", headers=target_headers).status_code in (401, 403)
    assert (
        auth_client.patch(target_path, headers=headers, json={"is_active": True}).status_code == 200
    )
    assert auth_client.get("/api/v1/users/me", headers=target_headers).status_code == 401
    assert auth_client.post("/api/v1/auth/refresh").status_code == 401
    page = auth_client.get("/api/v1/admin/users?q=OTHER&limit=1", headers=headers).json()
    assert page["total"] == 1 and page["items"][0]["id"] == target["id"]
    assert auth_client.get("/api/v1/admin/users?q=%", headers=headers).json()["total"] == 0
    assert auth_client.get("/api/v1/admin/users?offset=2", headers=headers).json()["items"] == []
    logs = auth_client.get(
        f"/api/v1/admin/audit-logs?actor_id={admin['id']}&action=user.updated&limit=1",
        headers=headers,
    ).json()
    assert logs["total"] == 2 and len(logs["items"]) == 1
    log = logs["items"][0]
    assert log["actor_email"] == ACCOUNT["email"] and log["target_id"] == target["id"]
    assert log["created_at"].endswith("Z")
    assert log["data"]["after"] == {"is_active": True}
    assert auth_client.patch(target_path, headers=headers, json={}).status_code == 200
    assert len(database_query(auth_engine, select(AuditLog.id))) == 2
    for body in ({"is_admin": False}, {"is_active": False}):
        assert (
            auth_client.patch(
                f"/api/v1/admin/users/{admin['id']}", headers=headers, json=body
            ).json()["code"]
            == "SELF_ADMIN_CHANGE"
        )
    assert (
        auth_client.patch(
            f"/api/v1/admin/users/{uuid4()}", headers=headers, json={"is_active": False}
        ).status_code
        == 404
    )


@pytest.mark.parametrize(
    "body", [{"is_active": None}, {"is_admin": "true"}, {"email_verified": True}]
)
def test_admin_input_validation(auth_client, email_queue, auth_engine, body):
    headers = admin_headers(auth_client, email_queue, auth_engine)
    assert (
        auth_client.patch(f"/api/v1/admin/users/{uuid4()}", headers=headers, json=body).status_code
        == 422
    )


@pytest.mark.parametrize("query", ["limit=0", "limit=101", "offset=-1", "actor_id=bad"])
def test_admin_pagination_validation(auth_client, email_queue, auth_engine, query):
    headers = admin_headers(auth_client, email_queue, auth_engine)
    assert auth_client.get(f"/api/v1/admin/audit-logs?{query}", headers=headers).status_code == 422


def test_event_roles_are_scoped_and_admin_does_not_bypass(auth_client, email_queue, auth_engine):
    access = sign_in(auth_client, email_queue)
    headers = {"Authorization": f"Bearer {access}"}
    user_id = UUID(auth_client.get("/api/v1/users/me", headers=headers).json()["id"])
    event_id, other_event = uuid4(), uuid4()
    assert auth_client.get("/api/v1/users/me/event-roles", headers=headers).json() == []

    async def seed():
        async with async_sessionmaker(auth_engine)() as session:
            if await session.get(Event, event_id) is None:
                now = datetime.now(UTC)
                session.add(
                    Event(
                        id=event_id,
                        name="Role test",
                        slug=f"role-{event_id}",
                        registration_opens_at=now,
                        registration_closes_at=now + timedelta(days=1),
                        starts_at=now + timedelta(days=2),
                        ends_at=now + timedelta(days=3),
                    )
                )
                await session.flush()
            session.add_all(
                [
                    EventRole(user_id=user_id, event_id=event_id, role="judge"),
                    EventRole(user_id=user_id, event_id=event_id, role="mentor"),
                ]
            )
            await session.commit()

    asyncio.run(seed())
    roles = auth_client.get("/api/v1/users/me/event-roles", headers=headers).json()
    assert roles == [
        {"event_id": str(event_id), "role": "judge"},
        {"event_id": str(event_id), "role": "mentor"},
    ]
    path = "/api/v1/test-role/{event_id}"

    async def protected(user=Depends(require_event_role("judge"))):
        return {"id": str(user.id)}

    api.add_api_route(path, protected)
    try:
        assert auth_client.get(f"/api/v1/test-role/{event_id}", headers=headers).status_code == 200
        assert (
            auth_client.get(f"/api/v1/test-role/{other_event}", headers=headers).status_code == 403
        )
        database_query(auth_engine, update(User).values(is_admin=True))
        assert auth_client.get(f"/api/v1/test-role/{event_id}", headers=headers).status_code == 403
    finally:
        api.router.routes[:] = [
            route for route in api.router.routes if getattr(route, "path", None) != path
        ]
        api.openapi_schema = None
    with pytest.raises(IntegrityError):
        asyncio.run(seed())


def test_first_admin_bootstrap_and_audit_atomicity(auth_engine, auth_settings):
    async def check():
        factory = async_sessionmaker(auth_engine, expire_on_commit=False)
        async with factory() as session:
            service = AuthService(AuthRepository(session), auth_settings)
            user = await service.create_first_admin(RegisterInput(**ACCOUNT))
            assert user.is_admin and user.email_verified and user.is_active
            logs, total = await service.repository.list_audit_logs(None, "admin.created", 20, 0)
            assert total == 1 and logs[0].actor_id == user.id
        async with factory() as session:
            service = AuthService(AuthRepository(session), auth_settings)
            with pytest.raises(ApiError) as error:
                await service.create_first_admin(
                    RegisterInput(**{**ACCOUNT, "email": "second@example.com"})
                )
            assert error.value.code == "ADMIN_EXISTS"
        async with factory() as session:
            service = AuthService(AuthRepository(session), auth_settings)
            await service.write_audit_log(user.id, "rolled.back", "user", str(user.id), {})
            await session.rollback()
        async with factory() as session:
            assert (
                await session.scalar(select(AuditLog.id).where(AuditLog.action == "rolled.back"))
                is None
            )

    asyncio.run(check())


def test_admin_change_rolls_back_when_audit_fails(
    auth_client, email_queue, auth_engine, monkeypatch
):
    headers = admin_headers(auth_client, email_queue, auth_engine)
    target = register(auth_client, {**ACCOUNT, "email": "target@example.com"})

    async def fail_audit(*args, **kwargs):
        raise ApiError(503, "AUDIT_UNAVAILABLE", "Audit unavailable")

    monkeypatch.setattr(AuthRepository, "write_audit_log", fail_audit)
    response = auth_client.patch(
        f"/api/v1/admin/users/{target['id']}", headers=headers, json={"is_admin": True}
    )
    assert response.status_code == 503
    assert database_query(
        auth_engine, select(User.is_admin).where(User.id == UUID(target["id"]))
    ) == [False]


def test_reset_rejects_short_password_and_disabled_account(auth_client, email_queue, auth_engine):
    sign_in(auth_client, email_queue)
    auth_client.post("/api/v1/auth/forgot-password", json={"email": ACCOUNT["email"]})
    raw = verification_token(email_queue)
    assert (
        auth_client.post(
            "/api/v1/auth/reset-password", json={"token": raw, "new_password": "short"}
        ).status_code
        == 422
    )
    database_query(auth_engine, update(User).values(is_active=False))
    assert (
        auth_client.post(
            "/api/v1/auth/reset-password", json={"token": raw, "new_password": "New password 123"}
        ).json()["code"]
        == "INVALID_TOKEN"
    )
