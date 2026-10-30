import asyncio
from time import perf_counter, time
from unittest.mock import AsyncMock, MagicMock, Mock

import pytest
from sqlalchemy.exc import SQLAlchemyError

from app.core.errors import ApiError
from app.integrations import system_monitor
from app.main import api
from app.modules.auth.repository import AuthRepository
from tests.test_auth import register
from tests.test_auth_admin import admin_headers
from worker import scheduler
from worker.celery_app import celery_app
from worker.scheduler import HeartbeatScheduler


@pytest.fixture
def probes(monkeypatch):
    redis = AsyncMock()
    beat = AsyncMock(return_value=time())
    workers = Mock(return_value={"celery"})
    monkeypatch.setattr(system_monitor, "ping_redis", redis)
    monkeypatch.setattr(system_monitor, "beat_heartbeat", beat)
    monkeypatch.setattr(system_monitor, "worker_queues", workers)
    return redis, beat, workers


def statuses(response):
    return {item["name"]: item for item in response.json()["services"]}


def test_admin_system_counts_and_openapi(auth_client, email_queue, auth_engine, probes):
    headers = admin_headers(auth_client, email_queue, auth_engine)
    target = register(
        auth_client,
        {"email": "other@example.com", "password": "Other password 123", "full_name": "Other"},
    )
    auth_client.patch(
        f"/api/v1/admin/users/{target['id']}", json={"is_active": False}, headers=headers
    )
    response = auth_client.get("/api/v1/admin/system", headers=headers)
    assert response.status_code == 200
    assert response.headers["cache-control"] == "no-store"
    data = response.json()
    assert data["server_time"].endswith("Z")
    assert data["data"] == {
        "users": 2,
        "active_users": 1,
        "admins": 1,
        "events": 0,
        "teams": 0,
        "submissions": 0,
        "commits": 0,
        "ai_reviews": 0,
        "audit_logs": 1,
        "database_bytes": None,
        "storage_bytes": None,
    }
    state = statuses(response)
    assert set(state) == {"database", "redis", "worker", "beat", "email_queue", "storage"}
    assert all(state[name]["status"] == "ok" for name in state if name != "storage")
    assert state["storage"]["status"] == "not_configured"
    assert all(value["latency_ms"] >= 0 for name, value in state.items() if name != "storage")
    api.openapi_schema = None
    operation = api.openapi()["paths"]["/api/v1/admin/system"]["get"]
    assert operation["security"] == [{"HTTPBearer": []}]
    assert operation["responses"]["200"]["content"]["application/json"]["schema"]["$ref"].endswith(
        "SystemOverview"
    )


def test_system_does_not_probe_before_auth_or_for_non_admin(auth_client, email_queue, probes):
    from tests.test_auth import sign_in

    assert auth_client.get("/api/v1/admin/system").status_code == 401
    token = sign_in(auth_client, email_queue)
    assert (
        auth_client.get(
            "/api/v1/admin/system", headers={"Authorization": f"Bearer {token}"}
        ).status_code
        == 403
    )
    for probe in probes:
        probe.assert_not_called()


def test_system_isolated_failures_and_no_provider_details(
    auth_client, email_queue, auth_engine, probes, monkeypatch
):
    headers = admin_headers(auth_client, email_queue, auth_engine)
    redis, beat, workers = probes
    secret = "redis://username:password@private-host/token-secret"
    redis.side_effect = RuntimeError(secret)
    beat.side_effect = RuntimeError(secret)
    workers.side_effect = RuntimeError(secret)
    monkeypatch.setattr(AuthRepository, "system_data", AsyncMock(side_effect=RuntimeError(secret)))
    response = auth_client.get("/api/v1/admin/system", headers=headers)
    assert response.status_code == 200
    state = statuses(response)
    assert state["database"]["status"] == "down"
    assert state["redis"]["status"] == "down"
    assert state["worker"]["status"] == "degraded"
    assert state["beat"]["status"] == "degraded"
    assert "password" not in response.text and "token-secret" not in response.text
    assert response.json()["data"]["users"] == 0


@pytest.mark.parametrize(
    "timestamp,expected",
    [(None, "down"), (-100, "down"), (float("nan"), "degraded"), (float("inf"), "degraded")],
)
def test_system_stale_or_invalid_beat(
    auth_client, email_queue, auth_engine, probes, timestamp, expected
):
    headers = admin_headers(auth_client, email_queue, auth_engine)
    probes[1].return_value = timestamp
    response = auth_client.get("/api/v1/admin/system", headers=headers)
    assert statuses(response)["beat"]["status"] == expected
    assert statuses(response)["redis"]["status"] == "ok"


@pytest.mark.parametrize(
    "queues,worker_status,email_status",
    [(None, "degraded", "degraded"), ({"ai-review"}, "ok", "degraded"), (set(), "ok", "degraded")],
)
def test_worker_must_consume_mail_queue(
    auth_client, email_queue, auth_engine, probes, queues, worker_status, email_status
):
    headers = admin_headers(auth_client, email_queue, auth_engine)
    probes[2].return_value = queues
    response = auth_client.get("/api/v1/admin/system", headers=headers)
    assert statuses(response)["worker"]["status"] == worker_status
    assert statuses(response)["email_queue"]["status"] == email_status


def test_probes_have_parallel_deadlines(auth_client, email_queue, auth_engine, probes, monkeypatch):
    headers = admin_headers(auth_client, email_queue, auth_engine)
    started = set()

    def stalled(name):
        async def wait(*args):
            started.add(name)
            await asyncio.Event().wait()

        return wait

    monkeypatch.setattr(AuthRepository, "system_data", stalled("database"))
    monkeypatch.setattr(system_monitor, "ping_redis", stalled("redis"))
    monkeypatch.setattr(system_monitor, "beat_heartbeat", stalled("beat"))
    start = perf_counter()
    response = auth_client.get("/api/v1/admin/system", headers=headers)
    assert response.status_code == 200 and perf_counter() - start < 3.5
    assert started == {"database", "redis", "beat"}
    assert statuses(response)["database"]["status"] == "down"
    assert statuses(response)["worker"]["status"] == "ok"


def test_auth_database_failure_stops_probes(
    auth_client, email_queue, auth_engine, probes, monkeypatch
):
    headers = admin_headers(auth_client, email_queue, auth_engine)
    monkeypatch.setattr(
        AuthRepository,
        "session_user",
        AsyncMock(side_effect=ApiError(503, "AUTH_UNAVAILABLE", "Authentication unavailable")),
    )
    response = auth_client.get("/api/v1/admin/system", headers=headers)
    assert response.status_code == 503 and response.json()["code"] == "AUTH_UNAVAILABLE"
    for probe in probes:
        probe.assert_not_called()


@pytest.mark.parametrize(
    "failure",
    [
        SQLAlchemyError("secret connection string"),
        ConnectionRefusedError("secret"),
        TimeoutError("secret"),
    ],
)
def test_repository_sanitizes_auth_database_errors(failure):
    session = AsyncMock()
    session.scalar.side_effect = failure

    async def check():
        from datetime import UTC, datetime
        from uuid import uuid4

        with pytest.raises(ApiError) as error:
            await AuthRepository(session).session_user(uuid4(), uuid4(), datetime.now(UTC))
        assert error.value.code == "AUTH_UNAVAILABLE" and "secret" not in error.value.detail

    asyncio.run(check())


@pytest.mark.parametrize(
    "replies,expected",
    [
        (None, None),
        (
            {"worker-a": [{"name": "celery"}], "worker-b": [{"name": "ai-review"}]},
            {"celery", "ai-review"},
        ),
    ],
)
def test_worker_inspection_is_bounded_and_keeps_current_app(monkeypatch, replies, expected):
    constructor = MagicMock()
    app = constructor.return_value.__enter__.return_value
    connection = app.connection_for_write.return_value.__enter__.return_value
    app.control.inspect.return_value.active_queues.return_value = replies
    monkeypatch.setattr(system_monitor, "Celery", constructor)
    assert system_monitor.worker_queues("redis://test/0") == expected
    constructor.assert_called_once_with(
        "seal-monitor", broker="redis://test/0", set_as_current=False
    )
    connection.ensure_connection.assert_called_once_with(max_retries=0, timeout=0.5)
    app.control.inspect.assert_called_once_with(timeout=0.8, connection=connection)


def test_scheduler_heartbeat_does_not_depend_on_worker(monkeypatch):
    heartbeat = Mock()
    clock = Mock(return_value=0)
    monkeypatch.setattr(scheduler, "publish_beat_heartbeat", heartbeat)
    monkeypatch.setattr(scheduler, "monotonic", clock)
    monkeypatch.setattr(scheduler.PersistentScheduler, "tick", lambda *args, **kwargs: 300)
    instance = HeartbeatScheduler(app=celery_app, lazy=True)
    assert instance.tick() == 30
    clock.return_value = 29
    instance.tick()
    assert heartbeat.call_count == 1
    clock.return_value = 30
    instance.tick()
    assert heartbeat.call_count == 2


def test_publish_beat_heartbeat_is_expiring_and_safe(monkeypatch):
    client = MagicMock()
    client.__enter__.return_value = client
    monkeypatch.setattr(system_monitor.Redis, "from_url", lambda *args, **kwargs: client)
    system_monitor.publish_beat_heartbeat("redis://test/0")
    args, kwargs = client.set.call_args
    assert args[0] == system_monitor.BEAT_HEARTBEAT_KEY
    assert float(args[1]) > 0 and kwargs["ex"] == 120


def test_scheduler_survives_redis_failure(monkeypatch, caplog):
    from redis.exceptions import ConnectionError

    monkeypatch.setattr(
        scheduler, "publish_beat_heartbeat", Mock(side_effect=ConnectionError("secret"))
    )
    monkeypatch.setattr(scheduler.PersistentScheduler, "tick", lambda *args, **kwargs: 10)
    instance = HeartbeatScheduler(app=celery_app, lazy=True)
    assert instance.tick() == 10
    assert "secret" not in caplog.text
