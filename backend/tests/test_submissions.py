import asyncio
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, Mock
from uuid import UUID, uuid4

import pytest
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.core.errors import ApiError
from app.integrations import github_client, storage
from app.modules.auth.models import AuditLog, EventRole
from app.modules.events.models import Event, Round, RoundEligibility
from app.modules.judging.service import JudgingService
from app.modules.submissions.models import FileUpload, Submission
from app.modules.teams.models import Team, TeamMember
from tests.test_auth import database_query
from tests.test_events_teams import (
    account,
    create_team,
    event_input,
    open_event,
    register_participant,
)


@pytest.fixture
def submission_world(world, monkeypatch):
    w = world
    open_event(w)
    register_participant(w, w.alice)
    team = create_team(w)
    w.team = team
    w.now = datetime.now(UTC)
    database_query(
        w.engine,
        update(Team)
        .where(Team.id == UUID(team["id"]))
        .values(status="approved", repo_url="https://github.com/example/public"),
    )
    database_query(
        w.engine,
        update(Event)
        .where(Event.id == UUID(w.event["id"]))
        .values(
            status="ongoing",
            registration_opens_at=w.now - timedelta(days=3),
            registration_closes_at=w.now - timedelta(days=2),
            starts_at=w.now - timedelta(days=1),
            ends_at=w.now + timedelta(days=3),
        ),
    )
    database_query(
        w.engine,
        update(Round)
        .where(Round.id == UUID(w.round["id"]))
        .values(
            starts_at=w.now - timedelta(hours=1),
            submission_deadline=w.now + timedelta(hours=2),
            ends_at=w.now + timedelta(days=1),
        ),
    )
    w.path = f"/api/v1/teams/{team['id']}/rounds/{w.round['id']}/submissions"
    w.body = {"repo_url": "https://github.com/example/public", "file_keys": []}
    w.sha = AsyncMock(return_value="a" * 40)
    monkeypatch.setattr(github_client, "head_sha", w.sha)
    w.objects = {}
    w.sealed = {}

    class FakeStorage:
        def __init__(self, settings):
            pass

        def presign(self, key, content_type, size):
            return f"https://storage.example/{key}?expires=600", {
                "public_id": key,
                "type": "authenticated",
                "overwrite": "false",
                "timestamp": "test-timestamp",
                "api_key": "test-key",
                "signature": "test-signature",
            }

        def seal(self, source, target, filename, content_type, size):
            if source not in w.objects:
                raise ApiError(422, "FILE_NOT_UPLOADED", "Missing")
            w.sealed[target] = w.objects[source]

        def download(self, key, filename):
            assert key in w.sealed
            return f"https://storage.example/{key}?expires=300"

        def delete_temporary(self, key):
            w.objects.pop(key, None)

        def discard_unsubmitted(self, key):
            w.sealed.pop(key, None)

    w.storage = FakeStorage
    monkeypatch.setattr(storage, "Storage", FakeStorage)
    return w


def submit(w, key="receipt-1", *, person=None, body=None):
    return w.client.post(
        w.path, headers={**(person or w.alice).headers, "Idempotency-Key": key}, json=body or w.body
    )


def presign(w, *, person=None, **changes):
    return w.client.post(
        "/api/v1/uploads/presign",
        headers=(person or w.alice).headers,
        json={
            "team_id": w.team["id"],
            "filename": "slides.pdf",
            "content_type": "application/pdf",
            "size": 12,
            **changes,
        },
    )


def test_receipt_versions_pagination_and_audit(submission_world):
    w = submission_world
    first = submit(w)
    assert first.status_code == 201, first.text
    assert first.json()["version"] == 1 and first.json()["commit_sha"] == "a" * 40
    assert first.json()["submitted_at"].endswith("Z")
    w.sha.return_value = "b" * 40
    second = submit(w, "second")
    assert second.status_code == 201 and second.json()["version"] == 2
    page = w.client.get(w.path, headers=w.alice.headers)
    assert page.headers["cache-control"] == "no-store"
    assert page.json()["total"] == 2
    assert [(s["version"], s["is_final"]) for s in page.json()["items"]] == [(2, True), (1, False)]
    assert (
        w.client.get(w.path + "?limit=1&offset=1", headers=w.alice.headers).json()["items"][0]["id"]
        == first.json()["id"]
    )
    assert w.client.get(w.path + "?limit=101", headers=w.alice.headers).status_code == 422
    detail = w.client.get(f"/api/v1/submissions/{first.json()['id']}", headers=w.admin.headers)
    assert detail.status_code == 200 and detail.json()["commit_sha"] == "a" * 40
    assert (
        len(
            database_query(
                w.engine, select(AuditLog.id).where(AuditLog.action == "submission.created")
            )
        )
        == 2
    )


def test_idempotency_after_deadline_conflict_and_authorization_first(submission_world):
    w = submission_world
    first = submit(w).json()
    database_query(
        w.engine,
        update(Round)
        .where(Round.id == UUID(w.round["id"]))
        .values(submission_deadline=w.now - timedelta(seconds=1)),
    )
    repeat = submit(w)
    assert repeat.status_code == 201 and repeat.json() == first
    assert w.sha.await_count == 1
    assert (
        submit(w, body={**w.body, "description": "changed"}).json()["code"]
        == "IDEMPOTENCY_CONFLICT"
    )
    assert submit(w, "new").json()["code"] == "DEADLINE_PASSED"
    database_query(
        w.engine,
        update(TeamMember).where(TeamMember.team_id == UUID(w.team["id"])).values(status="pending"),
    )
    assert submit(w).status_code == 403
    assert len(database_query(w.engine, select(Submission.id))) == 1


@pytest.mark.parametrize(
    "position,accepted",
    [
        ("before_start", False),
        ("start", True),
        ("before_deadline", True),
        ("deadline", False),
        ("after_deadline", False),
    ],
)
def test_exact_server_deadline(submission_world, monkeypatch, position, accepted):
    w = submission_world
    fixed = w.now.replace(microsecond=0)
    start = fixed - timedelta(hours=1)
    deadline = fixed + timedelta(hours=1)
    database_query(
        w.engine,
        update(Round)
        .where(Round.id == UUID(w.round["id"]))
        .values(starts_at=start, submission_deadline=deadline),
    )
    times = {
        "before_start": start - timedelta(microseconds=1),
        "start": start,
        "before_deadline": deadline - timedelta(microseconds=1),
        "deadline": deadline,
        "after_deadline": deadline + timedelta(seconds=1),
    }

    class Clock:
        @staticmethod
        def now(tz):
            return times[position]

    monkeypatch.setattr("app.modules.submissions.service.datetime", Clock)
    response = submit(w)
    assert response.status_code == (201 if accepted else 409), response.text
    if not accepted:
        assert response.json()["code"] == (
            "ROUND_NOT_OPEN" if position == "before_start" else "DEADLINE_PASSED"
        )


@pytest.mark.parametrize("status", ["draft", "open", "judging", "closed"])
def test_event_status_blocks_submission(submission_world, status):
    w = submission_world
    database_query(
        w.engine, update(Event).where(Event.id == UUID(w.event["id"])).values(status=status)
    )
    assert submit(w).json()["code"] == "ROUND_NOT_OPEN"
    assert presign(w).json()["code"] == "ROUND_NOT_OPEN"


def test_pending_member_admin_and_other_team_forbidden(submission_world):
    w = submission_world
    receipt = submit(w).json()
    bob = account(w.client, w.engine, "bob")

    async def member():
        async with async_sessionmaker(w.engine)() as session:
            session.add(
                TeamMember(
                    team_id=UUID(w.team["id"]),
                    event_id=UUID(w.event["id"]),
                    user_id=UUID(bob.id),
                    status="pending",
                )
            )
            await session.commit()

    asyncio.run(member())
    for actor in (w.admin, w.organizer, bob):
        assert submit(w, "forbidden", person=actor).status_code == 403
        assert presign(w, person=actor).status_code == 403
    for path in (w.path, f"/api/v1/submissions/{receipt['id']}"):
        assert w.client.get(path, headers=bob.headers).status_code == 403
        assert w.client.get(path, headers=w.admin.headers).status_code == 200
    database_query(
        w.engine,
        update(TeamMember).where(TeamMember.user_id == UUID(bob.id)).values(status="active"),
    )
    assert presign(w, person=bob).status_code == 200
    assert submit(w, person=bob).json()["code"] == "NOT_TEAM_LEADER"


def test_cross_event_round_and_team_ids(submission_world):
    w = submission_world
    event = w.client.post(
        "/api/v1/events", headers=w.admin.headers, json=event_input(w.organizer, "other-event")
    ).json()
    path = f"/api/v1/events/{event['id']}/rounds/{w.round['id']}/submissions"
    assert w.client.get(path, headers=w.admin.headers).status_code == 404
    wrong = w.path.replace(w.round["id"], str(uuid4()))
    assert w.client.get(wrong, headers=w.admin.headers).status_code == 404
    assert (
        w.client.post(
            wrong, headers={**w.alice.headers, "Idempotency-Key": "wrong"}, json=w.body
        ).status_code
        == 404
    )
    bob = account(w.client, w.engine, "stranger")
    assert submit(w, person=bob).status_code == 403
    assert w.client.get(w.path, headers=bob.headers).status_code == 403
    assert (
        w.client.get(f"/api/v1/submissions/{uuid4()}", headers=w.admin.headers).status_code == 404
    )


def test_later_round_requires_explicit_eligibility_and_freeze(submission_world, monkeypatch):
    w = submission_world
    second = uuid4()

    async def add():
        async with async_sessionmaker(w.engine)() as session:
            session.add(
                Round(
                    id=second,
                    event_id=UUID(w.event["id"]),
                    name="Round 2",
                    order=2,
                    starts_at=w.now - timedelta(minutes=10),
                    submission_deadline=w.now + timedelta(hours=1),
                    ends_at=w.now + timedelta(hours=2),
                )
            )
            await session.commit()

    asyncio.run(add())
    w.path = w.path.replace(w.round["id"], str(second))
    assert submit(w).json()["code"] == "ROUND_NOT_ELIGIBLE"

    async def allow():
        async with async_sessionmaker(w.engine)() as session:
            session.add(
                RoundEligibility(
                    round_id=second, team_id=UUID(w.team["id"]), source_round_id=UUID(w.round["id"])
                )
            )
            await session.commit()

    asyncio.run(allow())
    assert submit(w).json()["code"] == "ROUND_NOT_ELIGIBLE"
    monkeypatch.setattr(JudgingService, "results_ready", AsyncMock(return_value=True))
    assert submit(w).status_code == 201
    monkeypatch.setattr(JudgingService, "submissions_frozen", AsyncMock(return_value=True))
    assert submit(w, "new").json()["code"] == "SUBMISSIONS_FROZEN"
    assert submit(w).status_code == 201


def test_presign_ownership_upload_and_immutable_file(submission_world):
    w = submission_world
    upload = presign(w)
    assert upload.status_code == 200, upload.text
    assert upload.json()["method"] == "POST" and upload.json()["headers"] == {}
    assert upload.json()["fields"]["type"] == "authenticated"
    assert upload.json()["fields"]["overwrite"] == "false"
    key = upload.json()["file_key"]
    assert key.startswith("uploads/") and "slides.pdf" not in key
    assert submit(w, body={**w.body, "file_keys": [key]}).json()["code"] == "FILE_NOT_UPLOADED"
    w.objects[key] = b"%PDF-content"
    receipt = submit(w, body={**w.body, "file_keys": [key]}).json()
    assert receipt["files"][0]["filename"] == "slides.pdf"
    w.objects[key] = b"overwritten after receipt"
    detail = w.client.get(f"/api/v1/submissions/{receipt['id']}", headers=w.admin.headers)
    assert detail.status_code == 200 and "submissions/" in detail.json()["files"][0]["download_url"]
    assert list(w.sealed.values()) == [b"%PDF-content"]
    assert (
        submit(w, "reuse", body={**w.body, "file_keys": [key]}).json()["code"]
        == "FILE_NOT_UPLOADED"
    )
    assert (
        submit(w, "foreign", body={**w.body, "file_keys": [f"uploads/{uuid4()}/{uuid4()}"]}).json()[
            "code"
        ]
        == "FILE_NOT_UPLOADED"
    )
    foreign = presign(w).json()["file_key"]
    other_team = uuid4()

    async def other():
        async with async_sessionmaker(w.engine)() as session:
            session.add(
                Team(
                    id=other_team,
                    event_id=UUID(w.event["id"]),
                    leader_id=UUID(w.alice.id),
                    name="Other",
                    status="approved",
                )
            )
            await session.flush()
            await session.execute(
                update(FileUpload).where(FileUpload.key == foreign).values(team_id=other_team)
            )
            await session.commit()

    asyncio.run(other())
    assert submit(w, "foreign-owned", body={**w.body, "file_keys": [foreign]}).status_code == 422


@pytest.mark.parametrize(
    "changes,code",
    [
        ({"filename": "a.exe"}, "FILE_TYPE_NOT_ALLOWED"),
        ({"content_type": "application/zip"}, "FILE_TYPE_NOT_ALLOWED"),
        ({"size": storage.MAX_SIZE + 1}, "FILE_TOO_LARGE"),
        ({"filename": "../file.pdf"}, "VALIDATION_ERROR"),
        ({"size": 1.5}, "VALIDATION_ERROR"),
    ],
)
def test_upload_validation(submission_world, changes, code):
    response = presign(submission_world, **changes)
    assert response.status_code == 422 and response.json()["code"] == code


def test_not_approved_repo_failure_and_payload_validation(submission_world):
    w = submission_world
    assert (
        submit(w, body={**w.body, "repo_url": "https://github.com/other/repo"}).json()["code"]
        == "REPO_MISMATCH"
    )
    assert submit(w, body={**w.body, "demo_url": "file:///etc/passwd"}).status_code == 422
    assert submit(w, body={**w.body, "submitted_at": "2020-01-01"}).status_code == 422
    assert w.client.post(w.path, headers=w.alice.headers, json=w.body).status_code == 422
    w.sha.side_effect = ApiError(503, "REPO_UNAVAILABLE", "Unavailable")
    assert submit(w).json()["code"] == "REPO_UNAVAILABLE"
    assert database_query(w.engine, select(Submission.id)) == []
    database_query(
        w.engine, update(Team).where(Team.id == UUID(w.team["id"])).values(status="pending")
    )
    assert submit(w).json()["code"] == "TEAM_NOT_APPROVED"
    assert presign(w).json()["code"] == "TEAM_NOT_APPROVED"


def test_round_listing_includes_unsubmitted_teams(submission_world):
    w = submission_world
    path = f"/api/v1/events/{w.event['id']}/rounds/{w.round['id']}/submissions"
    result = w.client.get(path, headers=w.organizer.headers)
    assert result.json() == {
        "items": [{"team_id": w.team["id"], "name": w.team["name"], "submission": None}],
        "total": 1,
    }
    submit(w)
    submit(w, "v2")
    assert (
        w.client.get(path, headers=w.admin.headers).json()["items"][0]["submission"]["version"] == 2
    )
    assert w.client.get(path, headers=w.alice.headers).status_code == 403


def test_mentor_requires_real_assignment_hook(submission_world, monkeypatch):
    w = submission_world
    mentor = account(w.client, w.engine, "mentor")

    async def grant():
        async with async_sessionmaker(w.engine)() as session:
            session.add(
                EventRole(event_id=UUID(w.event["id"]), user_id=UUID(mentor.id), role="mentor")
            )
            await session.commit()

    asyncio.run(grant())
    receipt = submit(w).json()
    path = f"/api/v1/submissions/{receipt['id']}"
    assert w.client.get(path, headers=mentor.headers).status_code == 403

    async def assigned(self, user_id, team_id, round_id):
        return (
            user_id == UUID(mentor.id)
            and team_id == UUID(w.team["id"])
            and round_id == UUID(w.round["id"])
        )

    monkeypatch.setattr(JudgingService, "can_read_submission", assigned)
    assert w.client.get(path, headers=mentor.headers).status_code == 200
    monkeypatch.setattr(JudgingService, "can_read_submission", AsyncMock(return_value=False))
    assert w.client.get(path, headers=mentor.headers).status_code == 403


def test_provider_delay_does_not_extend_deadline(submission_world):
    w = submission_world
    key = presign(w).json()["file_key"]
    w.objects[key] = b"%PDF-content"
    fixed = w.now + timedelta(hours=2)
    clock = Mock()
    clock.now.side_effect = [w.now, fixed]
    from unittest.mock import patch

    with patch("app.modules.submissions.service.datetime", clock):
        response = submit(w, body={**w.body, "file_keys": [key]})
        assert response.json()["code"] == "DEADLINE_PASSED"
    assert w.sealed == {}
    assert database_query(w.engine, select(Submission.id)) == []


def test_concurrent_receipts_and_versions_on_postgres(submission_world):
    w = submission_world
    if w.engine.dialect.name != "postgresql":
        pytest.skip("Row-lock concurrency requires PostgreSQL")
    with ThreadPoolExecutor(max_workers=2) as pool:
        responses = list(pool.map(lambda _: submit(w, "same"), range(2)))
    assert [r.status_code for r in responses] == [201, 201]
    assert responses[0].json()["id"] == responses[1].json()["id"]
    with ThreadPoolExecutor(max_workers=2) as pool:
        responses = list(pool.map(lambda k: submit(w, k), ["new-a", "new-b"]))
    assert all(r.status_code == 201 for r in responses)
    assert sorted(r.json()["version"] for r in responses) == [2, 3]
