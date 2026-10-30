import asyncio
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import UUID, uuid4

import httpx
import pytest
from pydantic import SecretStr
from redis.exceptions import ConnectionError as RedisConnectionError
from sqlalchemy import select, update

from app.core.errors import ApiError
from app.integrations import github_client, rate_limits
from app.modules.auth.models import AuditLog, User
from app.modules.events.models import Event
from app.modules.teams.models import Team, TeamMember
from tests.test_auth import database_query


def account(client, engine, name, *, admin=False):
    email = f"{name}@example.com"
    result = client.post(
        "/api/v1/auth/register",
        json={"email": email, "full_name": name, "password": "Test password 123!"},
    )
    assert result.status_code == 201, result.text
    user = result.json()
    database_query(
        engine,
        update(User).where(User.id == UUID(user["id"])).values(email_verified=True, is_admin=admin),
    )
    login = client.post(
        "/api/v1/auth/login", json={"email": email, "password": "Test password 123!"}
    )
    assert login.status_code == 200, login.text
    return SimpleNamespace(
        id=user["id"],
        email=email,
        headers={"Authorization": f"Bearer {login.json()['access_token']}"},
    )


def event_input(organizer, slug="seal-test"):
    now = datetime.now(UTC)
    return {
        "name": "SEAL test",
        "slug": slug,
        "organizer_email": organizer.email,
        "registration_opens_at": (now - timedelta(hours=1)).isoformat(),
        "registration_closes_at": (now + timedelta(days=1)).isoformat(),
        "starts_at": (now + timedelta(days=2)).isoformat(),
        "ends_at": (now + timedelta(days=3)).isoformat(),
        "min_team_size": 1,
        "max_team_size": 2,
    }


@pytest.fixture
def world(auth_client, auth_engine, auth_settings, monkeypatch):
    auth_settings.github_token = SecretStr("test-token")
    verify = AsyncMock(return_value="https://github.com/example/public")
    limiter = AsyncMock(return_value=True)
    monkeypatch.setattr(github_client, "verify_public_repo", verify)
    monkeypatch.setattr(rate_limits, "consume", limiter)
    admin = account(auth_client, auth_engine, "admin", admin=True)
    organizer = account(auth_client, auth_engine, "organizer")
    alice = account(auth_client, auth_engine, "alice")
    body = event_input(organizer)
    response = auth_client.post("/api/v1/events", headers=admin.headers, json=body)
    assert response.status_code == 201, response.text
    event = response.json()
    round_input = {
        "name": "Round 1",
        "order": 1,
        "starts_at": event["starts_at"],
        "submission_deadline": (
            datetime.fromisoformat(event["starts_at"].replace("Z", "+00:00")) + timedelta(hours=12)
        ).isoformat(),
        "ends_at": event["ends_at"],
    }
    response = auth_client.post(
        f"/api/v1/events/{event['id']}/rounds", headers=organizer.headers, json=round_input
    )
    assert response.status_code == 201, response.text
    return SimpleNamespace(
        client=auth_client,
        engine=auth_engine,
        admin=admin,
        organizer=organizer,
        alice=alice,
        event=event,
        round=response.json(),
        verify=verify,
        limiter=limiter,
    )


def open_event(w):
    response = w.client.post(
        f"/api/v1/events/{w.event['id']}/transition",
        headers=w.organizer.headers,
        json={"to_status": "open"},
    )
    assert response.status_code == 200, response.text


def register_participant(w, person):
    response = w.client.post(f"/api/v1/events/{w.event['id']}/register", headers=person.headers)
    assert response.status_code == 201, response.text


def create_team(w, person=None):
    person = person or w.alice
    response = w.client.post(
        f"/api/v1/events/{w.event['id']}/teams",
        headers=person.headers,
        json={"name": person.email.split("@")[0]},
    )
    assert response.status_code == 201, response.text
    return response.json()


def test_draft_visibility_slug_and_public_children(world):
    w = world
    for path in (
        f"/events/{w.event['id']}",
        "/events/by-slug/seal-test",
        f"/events/{w.event['id']}/rounds",
        f"/events/{w.event['id']}/teams/public",
    ):
        assert w.client.get(f"/api/v1{path}").status_code == 404
    assert w.client.get("/api/v1/events").json()["total"] == 0
    assert w.client.get("/api/v1/events", headers=w.admin.headers).json()["total"] == 1
    assert w.client.get("/api/v1/events", headers=w.organizer.headers).json()["total"] == 1
    roles = w.client.get(f"/api/v1/events/{w.event['id']}/roles", headers=w.admin.headers).json()[
        "items"
    ]
    assert len(roles) == 1 and roles[0]["user"]["id"] == w.organizer.id
    open_event(w)
    assert w.client.get("/api/v1/events/by-slug/seal-test").status_code == 200
    assert w.client.get(f"/api/v1/events/{w.event['id']}/rounds").json()["total"] == 1


def test_invalid_schedule_transition_and_admin_boundaries(world):
    w = world
    path = f"/api/v1/events/{w.event['id']}"
    assert (
        w.client.post(
            path + "/transition", headers=w.admin.headers, json={"to_status": "open"}
        ).status_code
        == 403
    )
    assert (
        w.client.post(
            path + "/transition", headers=w.organizer.headers, json={"to_status": "closed"}
        ).json()["code"]
        == "INVALID_STATUS_TRANSITION"
    )
    assert (
        w.client.patch(path, headers=w.admin.headers, json={"max_team_size": 3}).status_code == 403
    )
    assert (
        w.client.patch(path, headers=w.admin.headers, json={"description": "Updated"}).status_code
        == 200
    )
    assert (
        w.client.patch(path, headers=w.organizer.headers, json={"min_team_size": 3}).status_code
        == 422
    )
    assert (
        w.client.patch(path, headers=w.organizer.headers, json={"starts_at": None}).status_code
        == 422
    )
    assert (
        w.client.post(path + "/archive", headers=w.admin.headers, json={"archived": True}).json()[
            "code"
        ]
        == "EVENT_NOT_CLOSED"
    )
    open_event(w)
    assert (
        w.client.patch(path, headers=w.organizer.headers, json={"slug": "changed"}).status_code
        == 409
    )
    assert (
        w.client.post(
            path + "/transition", headers=w.organizer.headers, json={"to_status": "ongoing"}
        ).status_code
        == 409
    )


def test_track_prize_crud_and_cross_event_ids(world):
    w = world
    base = f"/api/v1/events/{w.event['id']}"
    track = w.client.post(base + "/tracks", headers=w.organizer.headers, json={"name": "AI"}).json()
    prize = w.client.post(
        base + "/prizes",
        headers=w.organizer.headers,
        json={"name": "Winner", "rank": 1, "value": "1234567890123456.78"},
    )
    assert prize.status_code == 201, prize.text
    assert prize.json()["value"] == "1234567890123456.78"
    audit = database_query(
        w.engine,
        select(AuditLog.data).where(
            AuditLog.target_id == prize.json()["id"], AuditLog.action == "prizes.created"
        ),
    )[0]
    assert audit["after"]["value"] == "1234567890123456.78"
    assert (
        w.client.patch(
            base + f"/tracks/{track['id']}",
            headers=w.organizer.headers,
            json={"description": "Updated"},
        ).status_code
        == 200
    )
    other = w.client.post(
        "/api/v1/events", headers=w.admin.headers, json=event_input(w.organizer, "other-event")
    ).json()
    assert (
        w.client.patch(
            f"/api/v1/events/{other['id']}/tracks/{track['id']}",
            headers=w.organizer.headers,
            json={"name": "Hacked"},
        ).status_code
        == 404
    )
    assert (
        w.client.delete(
            base + f"/prizes/{prize.json()['id']}", headers=w.organizer.headers
        ).status_code
        == 204
    )
    assert (
        w.client.delete(base + f"/tracks/{track['id']}", headers=w.organizer.headers).status_code
        == 204
    )
    assert (
        w.client.post(
            base + "/prizes",
            headers=w.organizer.headers,
            json={"name": "Bad", "rank": 0, "value": "-1"},
        ).status_code
        == 422
    )


def test_registration_roles_and_last_organizer(world):
    w = world
    open_event(w)
    path = f"/api/v1/events/{w.event['id']}"
    register_participant(w, w.alice)
    assert w.client.post(path + "/register", headers=w.admin.headers).status_code == 403
    assert w.client.post(path + "/register", headers=w.organizer.headers).status_code == 409
    assert (
        w.client.post(
            path + "/roles",
            headers=w.organizer.headers,
            json={"email": w.alice.email, "role": "judge"},
        ).json()["code"]
        == "ROLE_CONFLICT"
    )
    assert (
        w.client.post(
            path + "/roles",
            headers=w.organizer.headers,
            json={"email": w.alice.email, "role": "organizer"},
        ).status_code
        == 403
    )
    org_role = w.client.get(path + "/roles", headers=w.admin.headers).json()["items"][0]
    # Roles are sorted by creation timestamp; resolve the organizer explicitly.
    org_role = next(
        r
        for r in w.client.get(path + "/roles", headers=w.admin.headers).json()["items"]
        if r["role"] == "organizer"
    )
    assert (
        w.client.delete(path + f"/roles/{org_role['id']}", headers=w.admin.headers).json()["code"]
        == "LAST_ORGANIZER"
    )
    result = w.client.patch(
        f"/api/v1/admin/users/{w.organizer.id}", headers=w.admin.headers, json={"is_active": False}
    )
    assert result.status_code == 409 and result.json()["code"] == "LAST_ORGANIZER"
    assert (
        w.client.patch(
            f"/api/v1/admin/users/{w.alice.id}", headers=w.admin.headers, json={"is_admin": True}
        ).json()["code"]
        == "EVENT_ROLES_PRESENT"
    )
    assert w.client.delete(path + "/register", headers=w.alice.headers).status_code == 204
    assert (
        w.client.patch(
            f"/api/v1/admin/users/{w.alice.id}", headers=w.admin.headers, json={"is_admin": True}
        ).status_code
        == 200
    )


def test_staff_role_lifecycle_and_directory_privacy(world):
    w = world
    judge = account(w.client, w.engine, "judge")
    path = f"/api/v1/events/{w.event['id']}"
    result = w.client.post(
        path + "/roles", headers=w.organizer.headers, json={"email": judge.email, "role": "judge"}
    )
    assert result.status_code == 201
    assert (
        w.client.post(
            path + "/roles", headers=w.admin.headers, json={"email": judge.email, "role": "mentor"}
        ).status_code
        == 403
    )
    open_event(w)
    register_participant(w, w.alice)
    team = create_team(w)
    directory = w.client.get(path + "/team-directory", headers=judge.headers).json()
    assert directory["items"] == [{"id": team["id"], "name": team["name"], "track_id": None}]
    assert w.client.get(f"/api/v1/teams/{team['id']}", headers=judge.headers).status_code == 403
    assert (
        w.client.delete(
            path + f"/roles/{result.json()['id']}", headers=w.organizer.headers
        ).status_code
        == 204
    )
    assert w.client.get(path + "/team-directory", headers=judge.headers).status_code == 403


def test_team_join_pending_full_approve_and_public(world):
    w = world
    bob = account(w.client, w.engine, "bob")
    carol = account(w.client, w.engine, "carol")
    open_event(w)
    for person in (w.alice, bob, carol):
        register_participant(w, person)
    team = create_team(w)
    path = f"/api/v1/teams/{team['id']}"
    pending = w.client.post(
        "/api/v1/teams/join", headers=bob.headers, json={"invite_code": team["invite_code"]}
    )
    assert pending.status_code == 200, pending.text
    assert "invite_code" not in pending.json() and pending.json().get("repo_url") is None
    assert (
        len(pending.json()["members"]) == 1 and pending.json()["members"][0]["user"]["id"] == bob.id
    )
    assert (
        w.client.post(
            "/api/v1/teams/join", headers=carol.headers, json={"invite_code": team["invite_code"]}
        ).json()["code"]
        == "TEAM_FULL"
    )
    assert (
        w.client.post(
            path + "/review", headers=w.organizer.headers, json={"status": "approved"}
        ).status_code
        == 409
    )
    assert (
        w.client.post(path + f"/members/{bob.id}/approve", headers=w.alice.headers).status_code
        == 200
    )
    assert (
        w.client.put(
            path + "/repo",
            headers=w.alice.headers,
            json={"repo_url": "https://github.com/example/public"},
        ).status_code
        == 200
    )
    assert (
        w.client.post(
            path + "/review", headers=w.organizer.headers, json={"status": "approved"}
        ).status_code
        == 200
    )
    public = w.client.get(f"/api/v1/events/{w.event['id']}/teams/public").json()
    assert len(public) == 1 and public[0]["member_count"] == 2
    assert set(public[0]) == {"id", "name", "track_id", "member_count", "approved_at"}
    assert (
        w.client.patch(path, headers=w.alice.headers, json={"name": "Updated"}).json()["status"]
        == "pending"
    )
    assert w.client.get(f"/api/v1/events/{w.event['id']}/teams/public").json() == []


def test_team_leadership_leave_and_soft_disband(world):
    w = world
    bob = account(w.client, w.engine, "bob")
    open_event(w)
    for person in (w.alice, bob):
        register_participant(w, person)
    team = create_team(w)
    path = f"/api/v1/teams/{team['id']}"
    w.client.post(
        "/api/v1/teams/join", headers=bob.headers, json={"invite_code": team["invite_code"]}
    )
    assert (
        w.client.delete(path + f"/members/{w.alice.id}", headers=w.alice.headers).json()["code"]
        == "TEAM_HAS_MEMBERS"
    )
    assert (
        w.client.post(
            path + "/transfer-leader", headers=w.alice.headers, json={"user_id": bob.id}
        ).status_code
        == 409
    )
    w.client.post(path + f"/members/{bob.id}/approve", headers=w.alice.headers)
    assert (
        w.client.post(
            path + "/transfer-leader", headers=w.alice.headers, json={"user_id": bob.id}
        ).json()["leader_id"]
        == bob.id
    )
    assert w.client.patch(path, headers=w.alice.headers, json={"name": "Nope"}).status_code == 403
    assert (
        w.client.delete(path + f"/members/{w.alice.id}", headers=w.alice.headers).status_code == 204
    )
    assert w.client.delete(path + f"/members/{bob.id}", headers=bob.headers).status_code == 204
    assert w.client.get(path, headers=bob.headers).status_code == 404
    stored = database_query(w.engine, select(Team.disbanded_at).where(Team.id == UUID(team["id"])))
    assert stored[0] is not None
    create_team(w, bob)


def test_admin_read_only_privacy_and_my_events(world):
    w = world
    open_event(w)
    register_participant(w, w.alice)
    team = create_team(w)
    path = f"/api/v1/teams/{team['id']}"
    admin_view = w.client.get(path, headers=w.admin.headers)
    assert admin_view.status_code == 200 and "invite_code" not in admin_view.json()
    assert w.client.patch(path, headers=w.admin.headers, json={"name": "No"}).status_code == 403
    assert (
        w.client.post(
            path + "/review", headers=w.admin.headers, json={"status": "rejected", "note": "No"}
        ).status_code
        == 403
    )
    assert w.client.get("/api/v1/me/events", headers=w.admin.headers).status_code == 403
    my = w.client.get("/api/v1/me/events", headers=w.alice.headers).json()
    assert my["total"] == 1 and my["items"][0]["team"]["id"] == team["id"]
    assert my["items"][0]["roles"] == ["participant"]
    listing = w.client.get("/api/v1/events", headers=w.admin.headers).json()
    assert listing["items"][0]["team_count"] == 1 and listing["items"][0]["participant_count"] == 1


def test_invite_rotation_expiry_withdraw_and_rate_limits(world, email_queue):
    w = world
    bob = account(w.client, w.engine, "bob")
    open_event(w)
    for person in (w.alice, bob):
        register_participant(w, person)
    team = create_team(w)
    path = f"/api/v1/teams/{team['id']}"
    rotated = w.client.post(path + "/invite-code", headers=w.alice.headers).json()["invite_code"]
    assert rotated != team["invite_code"]
    assert (
        w.client.post(
            "/api/v1/teams/join", headers=bob.headers, json={"invite_code": team["invite_code"]}
        ).status_code
        == 404
    )
    assert (
        w.client.post(
            path + "/invitations", headers=w.alice.headers, json={"email": "new@example.com"}
        ).status_code
        == 202
    )
    assert rotated in email_queue.call_args.kwargs["args"][2]
    assert (
        w.client.delete(
            f"/api/v1/events/{w.event['id']}/register", headers=w.alice.headers
        ).status_code
        == 409
    )
    w.limiter.return_value = False
    assert (
        w.client.post(
            "/api/v1/teams/join", headers=bob.headers, json={"invite_code": rotated}
        ).status_code
        == 429
    )
    w.limiter.side_effect = RedisConnectionError("secret")
    assert (
        w.client.post(
            path + "/invitations", headers=w.alice.headers, json={"email": "new@example.com"}
        ).status_code
        == 503
    )


def test_time_freeze_rejection_note_and_no_privilege_fields(world):
    w = world
    open_event(w)
    register_participant(w, w.alice)
    team = create_team(w)
    path = f"/api/v1/teams/{team['id']}"
    assert (
        w.client.post(
            path + "/review", headers=w.organizer.headers, json={"status": "rejected"}
        ).status_code
        == 422
    )
    assert (
        w.client.patch(path, headers=w.alice.headers, json={"status": "approved"}).status_code
        == 422
    )
    result = w.client.post(
        path + "/review",
        headers=w.organizer.headers,
        json={"status": "rejected", "note": "Need a repo"},
    )
    assert result.json()["review_note"] == "Need a repo"
    now = datetime.now(UTC)
    database_query(
        w.engine,
        update(Event)
        .where(Event.id == UUID(w.event["id"]))
        .values(
            registration_closes_at=now - timedelta(minutes=2), starts_at=now - timedelta(minutes=1)
        ),
    )
    assert (
        w.client.patch(path, headers=w.alice.headers, json={"name": "Late"}).json()["code"]
        == "TEAM_FROZEN"
    )
    assert (
        w.client.post(
            f"/api/v1/events/{w.event['id']}/transition",
            headers=w.organizer.headers,
            json={"to_status": "ongoing"},
        ).status_code
        == 200
    )
    assert (
        w.client.delete(path + f"/members/{w.alice.id}", headers=w.alice.headers).status_code == 409
    )


def test_archival_retains_member_access_and_hides_public(world):
    w = world
    open_event(w)
    register_participant(w, w.alice)
    team = create_team(w)
    database_query(
        w.engine, update(Event).where(Event.id == UUID(w.event["id"])).values(status="closed")
    )
    path = f"/api/v1/events/{w.event['id']}"
    assert (
        w.client.post(
            path + "/archive", headers=w.admin.headers, json={"archived": True}
        ).status_code
        == 200
    )
    assert w.client.get(path).status_code == 404
    assert w.client.get(path + "/rounds").status_code == 404
    assert w.client.get(path, headers=w.alice.headers).status_code == 200
    assert w.client.get(f"/api/v1/teams/{team['id']}", headers=w.alice.headers).status_code == 200
    assert w.client.get("/api/v1/events?include_archived=true").status_code == 403
    assert (
        w.client.get("/api/v1/events?include_archived=true", headers=w.admin.headers).json()[
            "total"
        ]
        == 1
    )


def test_duplicate_team_track_ownership_and_resource_constraints(world):
    w = world
    open_event(w)
    register_participant(w, w.alice)
    track = w.client.post(
        f"/api/v1/events/{w.event['id']}/tracks",
        headers=w.organizer.headers,
        json={"name": "Track"},
    ).json()
    team = create_team(w)
    assert (
        w.client.post(
            f"/api/v1/events/{w.event['id']}/teams",
            headers=w.alice.headers,
            json={"name": "Second"},
        ).json()["code"]
        == "ALREADY_IN_TEAM"
    )
    assert (
        w.client.patch(
            f"/api/v1/teams/{team['id']}", headers=w.alice.headers, json={"track_id": str(uuid4())}
        ).status_code
        == 404
    )
    assert (
        w.client.patch(
            f"/api/v1/teams/{team['id']}", headers=w.alice.headers, json={"track_id": track["id"]}
        ).status_code
        == 200
    )
    assert (
        w.client.delete(
            f"/api/v1/events/{w.event['id']}/tracks/{track['id']}", headers=w.organizer.headers
        ).json()["code"]
        == "RESOURCE_IN_USE"
    )
    actions = database_query(w.engine, select(AuditLog.action))
    assert "team.created" in actions and "team.updated" in actions


def test_simultaneous_join_cannot_overfill_postgres(world):
    w = world
    if w.engine.dialect.name != "postgresql":
        pytest.skip("Row locking is verified on dedicated PostgreSQL")
    bob, carol = account(w.client, w.engine, "bob"), account(w.client, w.engine, "carol")
    open_event(w)
    for person in (w.alice, bob, carol):
        register_participant(w, person)
    team = create_team(w)

    def join(person):
        return w.client.post(
            "/api/v1/teams/join", headers=person.headers, json={"invite_code": team["invite_code"]}
        ).status_code

    with ThreadPoolExecutor(max_workers=2) as pool:
        assert sorted(pool.map(join, (bob, carol))) == [200, 409]
    assert (
        len(
            database_query(
                w.engine, select(TeamMember.id).where(TeamMember.team_id == UUID(team["id"]))
            )
        )
        == 2
    )


@pytest.mark.parametrize(
    "url",
    [
        "http://github.com/a/b",
        "https://evil.example/a/b",
        "https://github.com/a/b?token=x",
        "https://github.com:443/a/b",
        "https://github.com/a/..",
    ],
)
def test_github_rejects_unsafe_urls(auth_settings, url):
    with pytest.raises(ApiError) as error:
        asyncio.run(github_client.verify_public_repo(url, auth_settings))
    assert error.value.status_code == 422


@pytest.mark.parametrize(
    "status,body,expected",
    [
        (200, {"private": False}, None),
        (200, [], 503),
        (200, {"private": True}, 422),
        (404, {}, 422),
        (401, {}, 503),
        (500, {}, 503),
    ],
)
def test_github_public_repo_check(auth_settings, monkeypatch, status, body, expected):
    auth_settings.github_token = SecretStr("secret")
    real_client = httpx.AsyncClient

    async def handler(request):
        assert request.url.host == "api.github.com"
        assert request.headers["Authorization"] == "Bearer secret"
        return httpx.Response(status, json=body)

    monkeypatch.setattr(
        github_client.httpx,
        "AsyncClient",
        lambda **kwargs: real_client(transport=httpx.MockTransport(handler), **kwargs),
    )
    if expected:
        with pytest.raises(ApiError) as error:
            asyncio.run(
                github_client.verify_public_repo(
                    "https://github.com/example/repo.git", auth_settings
                )
            )
        assert error.value.status_code == expected
    else:
        assert (
            asyncio.run(
                github_client.verify_public_repo(
                    "https://github.com/example/repo.git", auth_settings
                )
            )
            == "https://github.com/example/repo"
        )


def test_schedule_update_respects_team_capacity_and_invite_expiry(world):
    w = world
    bob = account(w.client, w.engine, "bob")
    open_event(w)
    for person in (w.alice, bob):
        register_participant(w, person)
    team = create_team(w)
    w.client.post(
        "/api/v1/teams/join", headers=bob.headers, json={"invite_code": team["invite_code"]}
    )
    base = f"/api/v1/events/{w.event['id']}"
    assert (
        w.client.patch(base, headers=w.organizer.headers, json={"max_team_size": 1}).json()["code"]
        == "TEAM_FULL"
    )
    deadline = datetime.now(UTC) + timedelta(hours=3)
    result = w.client.patch(
        base, headers=w.organizer.headers, json={"registration_closes_at": deadline.isoformat()}
    )
    assert result.status_code == 200, result.text
    current = w.client.get(f"/api/v1/teams/{team['id']}", headers=w.alice.headers).json()
    assert datetime.fromisoformat(current["invite_expires_at"].replace("Z", "+00:00")) == deadline


def test_individual_team_and_repeated_approval_are_safe(world):
    w = world
    base = f"/api/v1/events/{w.event['id']}"
    assert (
        w.client.patch(base, headers=w.organizer.headers, json={"max_team_size": 1}).status_code
        == 200
    )
    open_event(w)
    register_participant(w, w.alice)
    team = create_team(w)
    path = f"/api/v1/teams/{team['id']}"
    w.client.put(
        path + "/repo",
        headers=w.alice.headers,
        json={"repo_url": "https://github.com/example/public"},
    )
    approved = w.client.post(
        path + "/review", headers=w.organizer.headers, json={"status": "approved"}
    )
    assert approved.status_code == 200, approved.text
    repeated = w.client.post(
        path + "/review", headers=w.organizer.headers, json={"status": "approved"}
    )
    assert repeated.json()["reviewed_at"] == approved.json()["reviewed_at"]
    bob = account(w.client, w.engine, "bob")
    register_participant(w, bob)
    assert (
        w.client.post(
            "/api/v1/teams/join", headers=bob.headers, json={"invite_code": team["invite_code"]}
        ).json()["code"]
        == "TEAM_FULL"
    )


def test_review_queue_failure_preserves_saved_decision(world, email_queue):
    w = world
    open_event(w)
    register_participant(w, w.alice)
    team = create_team(w)
    email_queue.side_effect = RuntimeError("secret provider failure")
    response = w.client.post(
        f"/api/v1/teams/{team['id']}/review",
        headers=w.organizer.headers,
        json={"status": "rejected", "note": "Fix repo"},
    )
    assert response.status_code == 503 and response.json()["code"] == "EMAIL_QUEUE_UNAVAILABLE"
    assert (
        w.client.get(f"/api/v1/teams/{team['id']}", headers=w.alice.headers).json()["status"]
        == "rejected"
    )


def test_simultaneous_role_grant_and_admin_promotion_postgres(world):
    w = world
    if w.engine.dialect.name != "postgresql":
        pytest.skip("Concurrent policy is verified on dedicated PostgreSQL")
    target = account(w.client, w.engine, "target")

    def action(kind):
        if kind == "role":
            return w.client.post(
                f"/api/v1/events/{w.event['id']}/roles",
                headers=w.organizer.headers,
                json={"email": target.email, "role": "judge"},
            ).status_code
        return w.client.patch(
            f"/api/v1/admin/users/{target.id}", headers=w.admin.headers, json={"is_admin": True}
        ).status_code

    with ThreadPoolExecutor(max_workers=2) as pool:
        statuses = list(pool.map(action, ("role", "admin")))
    assert sorted(statuses) in ([200, 409], [201, 409])


def test_schema_has_typed_private_fields_and_no_shared_cache(world):
    w = world
    schema = w.client.get("/openapi.json").json()
    assert "members" in schema["components"]["schemas"]["TeamOutput"]["properties"]
    assert "slug" in schema["components"]["schemas"]["EventSummary"]["properties"]
    assert (
        w.client.get("/api/v1/events", headers=w.admin.headers).headers["cache-control"]
        == "no-store"
    )


def test_non_utc_input_is_persisted_as_utc(world):
    w = world
    body = event_input(w.organizer, "timezone-event")
    expected = datetime.fromisoformat(body["starts_at"])
    for key in ("registration_opens_at", "registration_closes_at", "starts_at", "ends_at"):
        body[key] = (
            datetime.fromisoformat(body[key]).astimezone(timezone(timedelta(hours=7))).isoformat()
        )
    response = w.client.post("/api/v1/events", headers=w.admin.headers, json=body)
    assert response.status_code == 201, response.text
    result = w.client.get(f"/api/v1/events/{response.json()['id']}", headers=w.admin.headers).json()
    assert result["starts_at"].endswith("Z")
    assert datetime.fromisoformat(result["starts_at"].replace("Z", "+00:00")) == expected
