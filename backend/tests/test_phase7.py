import asyncio
from io import BytesIO
from unittest.mock import AsyncMock, Mock
from uuid import UUID, uuid4

import pytest
from openpyxl import load_workbook
from sqlalchemy import create_engine, delete, select, update
from sqlalchemy.ext.asyncio import async_sessionmaker
from sqlalchemy.orm import Session

from app import realtime
from app.core.errors import ApiError
from app.integrations import mailer, system_monitor
from app.modules.auth.models import EventRole, User
from app.modules.notifications.jobs import NotificationJobs
from app.modules.notifications.models import NotificationDelivery, RealtimeOutbox
from app.modules.notifications.repository import NotificationRepository
from app.modules.reports.service import ReportService
from tests.test_auth import database_query
from tests.test_events_teams import account, create_team, open_event, register_participant
from tests.test_judging import call, complete


def test_announcements_audience_ownership_and_outbox(world):
    w = world
    open_event(w)
    register_participant(w, w.alice)
    outsider = account(w.client, w.engine, "outsider")
    base = f"/api/v1/events/{w.event['id']}"
    for audience in ("public", "all", "participants", "judges", "mentors"):
        response = w.client.post(
            base + "/announcements",
            headers=w.organizer.headers,
            json={
                "title": audience,
                "body": "Nội dung <plain text>",
                "audience": audience,
                "send_email": True,
            },
        )
        assert response.status_code == 201, response.text
    for actor, titles in (
        (None, {"public"}),
        (outsider, {"public"}),
        (w.alice, {"public", "all", "participants"}),
        (w.admin, {"public", "all", "participants", "judges", "mentors"}),
    ):
        response = w.client.get(base + "/announcements", headers=actor.headers if actor else {})
        assert {row["title"] for row in response.json()["items"]} == titles
    assert (
        w.client.post(
            base + "/announcements",
            headers=w.admin.headers,
            json={"title": "x", "body": "y", "audience": "all"},
        ).status_code
        == 403
    )
    assert (
        w.client.post(
            base + "/announcements",
            headers=w.organizer.headers,
            json={"title": " ", "body": "y", "audience": "all"},
        ).status_code
        == 422
    )
    inbox = w.client.get("/api/v1/me/notifications", headers=w.alice.headers).json()
    assert inbox["unread_count"] == 3
    notification_id = inbox["items"][0]["id"]
    assert (
        w.client.post(
            f"/api/v1/me/notifications/{notification_id}/read", headers=outsider.headers
        ).status_code
        == 404
    )
    for _ in range(2):
        assert (
            w.client.post(
                f"/api/v1/me/notifications/{notification_id}/read", headers=w.alice.headers
            ).status_code
            == 204
        )
    assert (
        w.client.get("/api/v1/me/notifications?unread=true", headers=w.alice.headers).json()[
            "total"
        ]
        == 2
    )
    assert (
        w.client.post("/api/v1/me/notifications/read-all", headers=w.alice.headers).status_code
        == 204
    )
    assert (
        w.client.get("/api/v1/me/notifications", headers=w.alice.headers).json()["unread_count"]
        == 0
    )
    deliveries = w.client.get(base + "/notification-deliveries", headers=w.admin.headers)
    assert deliveries.status_code == 200
    assert all(
        "payload" not in item and "recipient_key" not in item for item in deliveries.json()["items"]
    )
    assert (
        w.client.get(base + "/notification-deliveries", headers=w.alice.headers).status_code == 403
    )
    assert (
        w.client.get(
            base + "/notification-deliveries?status=secret", headers=w.organizer.headers
        ).status_code
        == 422
    )


def test_revoked_participant_loses_private_inbox(world):
    w = world
    open_event(w)
    register_participant(w, w.alice)
    base = f"/api/v1/events/{w.event['id']}/announcements"
    for audience in ("public", "participants"):
        assert (
            w.client.post(
                base,
                headers=w.organizer.headers,
                json={"title": audience, "body": "Private audience check", "audience": audience},
            ).status_code
            == 201
        )
    database_query(
        w.engine,
        delete(EventRole).where(
            EventRole.event_id == UUID(w.event["id"]), EventRole.user_id == UUID(w.alice.id)
        ),
    )
    inbox = w.client.get("/api/v1/me/notifications", headers=w.alice.headers).json()
    assert [item["title"] for item in inbox["items"]] == ["public"]


def test_reports_dashboard_filters_and_safe_files(world):
    w = world
    open_event(w)
    register_participant(w, w.alice)
    team = create_team(w)
    from app.modules.teams.models import Team

    database_query(
        w.engine,
        update(Team)
        .where(Team.id == UUID(team["id"]))
        .values(name='=HYPERLINK("https://invalid", "x")'),
    )
    base = f"/api/v1/events/{w.event['id']}"
    response = w.client.get(base + "/dashboard", headers=w.organizer.headers)
    assert response.status_code == 200, response.text
    assert response.json()["registrations"] == 1
    assert response.json()["teams_by_status"] == {"pending": 1}
    assert response.json()["commits_per_day"] == {}
    assert w.client.get(base + "/dashboard", headers=w.admin.headers).status_code == 403
    for actor in (w.alice, None):
        assert w.client.get(
            base + "/reports/export?type=teams&format=xlsx", headers=actor.headers if actor else {}
        ).status_code in {401, 403}
    export = w.client.get(base + "/reports/export?type=teams&format=xlsx", headers=w.admin.headers)
    assert export.status_code == 200, export.text
    cells = list(load_workbook(BytesIO(export.content)).active.rows)
    assert cells[1][1].value.startswith("=HYPERLINK")
    assert cells[1][1].data_type == "s"
    assert "invite_code" not in [c.value for c in cells[0]]
    pdf = w.client.get(base + "/reports/export?type=teams&format=pdf", headers=w.organizer.headers)
    assert pdf.status_code == 200 and pdf.content.startswith(b"%PDF")
    assert (
        w.client.get(
            base + f"/reports/export?type=teams&format=xlsx&round_id={uuid4()}",
            headers=w.admin.headers,
        ).status_code
        == 404
    )
    assert (
        w.client.get(
            base + f"/reports/export?type=teams&format=xlsx&track_id={uuid4()}",
            headers=w.admin.headers,
        ).status_code
        == 404
    )
    assert (
        w.client.get(
            base + "/reports/export?type=leaderboard&format=xlsx", headers=w.admin.headers
        ).status_code
        == 422
    )


def test_export_requires_locked_scores_and_publication_invalidations(judging_world):
    w = judging_world
    export = (
        f"/events/{w.event['id']}/reports/export?type=leaderboard&format=xlsx"
        f"&round_id={w.round['id']}"
    )
    assert call(w, "get", export, w.admin).status_code == 409
    complete(w)
    assert call(w, "post", w.base + "/lock").status_code == 204
    assert call(w, "get", export, w.admin).status_code == 200
    assert call(w, "post", w.base + "/publish").status_code == 204
    assert call(w, "post", w.base + "/unpublish", body={"reason": "correction"}).status_code == 204
    rows = database_query(w.engine, select(RealtimeOutbox.event))
    assert "leaderboard:updated" in rows and "leaderboard:unpublished" in rows
    inbox = call(w, "get", "/me/notifications", w.alice).json()
    assert {item["type"] for item in inbox["items"]} >= {"round.publish", "round.unpublish"}


def test_delivery_dedupe_unknown_and_realtime_retry(world, auth_settings, monkeypatch):
    w = world
    open_event(w)
    register_participant(w, w.alice)
    url = w.engine.url.set(
        drivername="sqlite" if w.engine.dialect.name == "sqlite" else "postgresql+psycopg"
    )
    engine = create_engine(url)
    send = Mock(side_effect=RuntimeError("ambiguous receipt"))
    emit = Mock()
    monkeypatch.setattr(mailer, "send_email", send)
    monkeypatch.setattr("app.modules.notifications.jobs.publish", emit)
    try:
        with Session(engine, expire_on_commit=False) as session:
            repo = NotificationRepository(session)
            repo.enqueue(
                UUID(w.event["id"]),
                "test:delivery",
                "announcement",
                [(UUID(w.alice.id), w.alice.email)],
                "Hello",
                "Body",
                "/notifications",
            )
            session.commit()
            jobs = NotificationJobs(session, auth_settings)
            assert jobs.deliver() == 1
            assert jobs.deliver() == 0
            assert send.call_count == 1 and emit.call_count == 1
            assert sorted(session.scalars(select(NotificationDelivery.status))) == [
                "sent",
                "unknown",
            ]
            repo.realtime("team:approved", f"event:{w.event['id']}", {"team_id": str(uuid4())})
            session.commit()
            emit.side_effect = RuntimeError("Redis unavailable")
            assert jobs.realtime() == 0
            emit.side_effect = None
            assert jobs.realtime() == 1
            assert jobs.realtime() == 0
    finally:
        engine.dispose()


def test_socket_scope_rechecked_after_revocation(world, auth_settings, monkeypatch):
    w = world
    open_event(w)
    monkeypatch.setattr(
        realtime, "session_factory", async_sessionmaker(w.engine, expire_on_commit=False)
    )
    monkeypatch.setattr(realtime, "get_settings", lambda: auth_settings)
    room = f"event:{w.event['id']}"
    token = w.organizer.headers["Authorization"].removeprefix("Bearer ")
    assert asyncio.run(realtime.authorized(None, room))
    assert not asyncio.run(realtime.authorized(None, room + ":organizer"))
    assert asyncio.run(realtime.authorized(token, room + ":organizer"))
    assert not asyncio.run(realtime.authorized(token, f"user:{w.alice.id}"))
    database_query(
        w.engine,
        delete(EventRole).where(
            EventRole.event_id == UUID(w.event["id"]), EventRole.user_id == UUID(w.organizer.id)
        ),
    )
    assert not asyncio.run(realtime.authorized(token, room + ":organizer"))
    assert (
        w.client.get(
            f"/api/v1/events/{w.event['id']}/reports/export?type=teams&format=xlsx",
            headers=w.organizer.headers,
        ).status_code
        == 403
    )
    database_query(
        w.engine, update(User).where(User.id == UUID(w.organizer.id)).values(is_active=False)
    )
    assert not asyncio.run(realtime.authorized(token, room + ":organizer"))


def test_socket_ai_visibility_and_pending_membership(ai_world, auth_settings, monkeypatch):
    from app.modules.events.models import Round
    from app.modules.teams.models import TeamMember
    from tests.test_ai_reviews import execute

    w = ai_world
    execute(w)
    monkeypatch.setattr(
        realtime, "session_factory", async_sessionmaker(w.engine, expire_on_commit=False)
    )
    monkeypatch.setattr(realtime, "get_settings", lambda: auth_settings)
    room = f"team:{w.team['id']}"
    token = w.alice.headers["Authorization"].removeprefix("Bearer ")
    payload = database_query(
        w.engine, select(RealtimeOutbox.payload).where(RealtimeOutbox.event == "ai_review:new")
    )[0]
    assert asyncio.run(realtime.authorized(token, room, "ai_review:new", payload))
    config = {**w.config, "ai_visible_to_participants": "never"}
    database_query(
        w.engine, update(Round).where(Round.id == UUID(w.round["id"])).values(ai_config=config)
    )
    assert not asyncio.run(realtime.authorized(token, room, "ai_review:new", payload))
    config["ai_visible_to_participants"] = "during"
    database_query(
        w.engine, update(Round).where(Round.id == UUID(w.round["id"])).values(ai_config=config)
    )
    database_query(
        w.engine,
        update(TeamMember).where(TeamMember.user_id == UUID(w.alice.id)).values(status="pending"),
    )
    assert not asyncio.run(realtime.authorized(token, room))


def test_export_limit_and_readiness(auth_client, monkeypatch):
    from types import SimpleNamespace

    events = SimpleNamespace(
        get=AsyncMock(), require_organizer=AsyncMock(), ensure_track=AsyncMock()
    )
    service = ReportService(
        SimpleNamespace(rows=AsyncMock(return_value=[{}] * 10001)), events, None
    )
    with pytest.raises(ApiError) as error:
        asyncio.run(service.export(None, uuid4(), "teams", "xlsx", None, None))
    assert error.value.code == "EXPORT_TOO_LARGE"
    monkeypatch.setattr(system_monitor, "ping_redis", AsyncMock())
    response = auth_client.get("/api/v1/ready")
    assert response.status_code == 200 and response.json() == {"status": "ready"}
    monkeypatch.setattr(
        system_monitor, "ping_redis", AsyncMock(side_effect=RuntimeError("internal endpoint"))
    )
    response = auth_client.get("/api/v1/ready")
    assert response.status_code == 503 and response.json() == {"status": "not_ready"}


@pytest.mark.parametrize("status", [403, 503])
def test_watch_closes_on_revocation_or_auth_outage_instead_of_silently_dropping_room(
    monkeypatch, status
):
    from types import SimpleNamespace

    server = SimpleNamespace(
        manager=SimpleNamespace(is_connected=Mock(return_value=True)),
        get_session=AsyncMock(return_value={"token": "fixture-token"}),
        rooms=Mock(return_value=["sid", f"event:{uuid4()}:organizer"]),
        leave_room=AsyncMock(),
        disconnect=AsyncMock(),
    )
    monkeypatch.setattr(realtime, "sio", server)
    monkeypatch.setattr(realtime, "ping_redis", AsyncMock())
    monkeypatch.setattr(realtime.asyncio, "sleep", AsyncMock())
    monkeypatch.setattr(
        realtime,
        "allowed",
        AsyncMock(
            side_effect=ApiError(
                status,
                "AUTH_UNAVAILABLE" if status == 503 else "FORBIDDEN",
                "Private provider detail",
            )
        ),
    )
    asyncio.run(realtime.watch("sid"))
    server.disconnect.assert_awaited_once_with("sid")
    server.leave_room.assert_not_called()


def test_authorization_backend_error_is_not_reported_as_revoked_permission(monkeypatch):
    monkeypatch.setattr(
        realtime,
        "allowed",
        AsyncMock(side_effect=ApiError(503, "AUTH_UNAVAILABLE", "private detail")),
    )
    with pytest.raises(ApiError) as error:
        asyncio.run(realtime.authorized("fixture-token", f"event:{uuid4()}:organizer"))
    assert error.value.status_code == 503


def test_in_app_delivery_does_not_wait_for_smtp_recipient_lock(world, auth_settings, monkeypatch):
    w = world
    if w.engine.dialect.name != "postgresql":
        pytest.skip("Recipient row locking requires PostgreSQL")
    open_event(w)
    register_participant(w, w.alice)
    engine = create_engine(
        w.engine.url.set(drivername="postgresql+psycopg"),
        connect_args={"options": "-c lock_timeout=1000"},
    )
    emit = Mock()
    monkeypatch.setattr("app.modules.notifications.jobs.publish", emit)
    try:
        with Session(engine, expire_on_commit=False) as setup:
            NotificationRepository(setup).enqueue(
                UUID(w.event["id"]),
                "test:smtp-lock",
                "announcement",
                [(UUID(w.alice.id), w.alice.email)],
                "Title",
                "Body",
                "/notifications",
                False,
            )
            setup.commit()
        with Session(engine) as smtp, Session(engine, expire_on_commit=False) as realtime_session:
            smtp.scalar(select(User).where(User.id == UUID(w.alice.id)).with_for_update())
            assert NotificationJobs(realtime_session, auth_settings).deliver(channel="in_app") == 1
            emit.assert_called_once()
    finally:
        engine.dispose()
