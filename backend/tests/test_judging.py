import asyncio
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import UUID, uuid4

import pytest
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.integrations import ranking_cache
from app.modules.auth.models import AuditLog
from app.modules.events.models import Event, Round
from app.modules.judging.models import (
    PublicationSnapshot,
    ResultEmail,
    RoundJudging,
    RubricCriterion,
)
from app.modules.ranking.service import calculate, rank_rows
from tests.test_auth import database_query
from tests.test_events_teams import account
from tests.test_submissions import submit


def call(w, method, path, person=None, body=None):
    return getattr(w.client, method)(
        "/api/v1" + path,
        headers=(person or w.organizer).headers,
        **({"json": body} if body is not None else {}),
    )


def grant(w, person, role):
    response = call(
        w, "post", f"/events/{w.event['id']}/roles", body={"email": person.email, "role": role}
    )
    assert response.status_code == 201, response.text
    return response.json()


@pytest.fixture
def judging_world(submission_world, monkeypatch):
    w = submission_world
    monkeypatch.setattr(ranking_cache, "read", AsyncMock(return_value=None))
    monkeypatch.setattr(ranking_cache, "write", AsyncMock())
    w.judges = [account(w.client, w.engine, f"judge{i}") for i in range(3)]
    w.mentor = account(w.client, w.engine, "mentor")
    for judge in w.judges:
        grant(w, judge, "judge")
    w.mentor_role = grant(w, w.mentor, "mentor")
    w.old_submission = submit(w).json()
    w.final = submit(w, "final-version").json()
    database_query(
        w.engine,
        update(Round)
        .where(Round.id == UUID(w.round["id"]))
        .values(submission_deadline=w.now - timedelta(minutes=1)),
    )
    # The receipt predates the deadline, as in a real submission.
    from app.modules.submissions.models import Submission

    database_query(w.engine, update(Submission).values(submitted_at=w.now - timedelta(minutes=2)))
    w.base = f"/events/{w.event['id']}/rounds/{w.round['id']}"
    w.team_base = f"/teams/{w.team['id']}"

    async def rubric():
        async with async_sessionmaker(w.engine, expire_on_commit=False)() as session:
            rows = [
                RubricCriterion(
                    round_id=UUID(w.round["id"]),
                    name="Quality",
                    description="",
                    weight=60,
                    max_score=10,
                    order=1,
                ),
                RubricCriterion(
                    round_id=UUID(w.round["id"]),
                    name="Impact",
                    description="",
                    weight=40,
                    max_score=20,
                    order=2,
                ),
            ]
            session.add_all(rows)
            await session.commit()
            return [str(c.id) for c in rows]

    w.criteria = asyncio.run(rubric())
    return w


def assign(w, judge=None):
    result = call(
        w,
        "post",
        w.base + "/assignments",
        body={"judge_id": (judge or w.judges[0]).id, "team_ids": [w.team["id"]]},
    )
    assert result.status_code == 200, result.text
    return result.json()


def score(w, assignment, judge, values=(8, 15), revision=0):
    result = call(
        w,
        "put",
        f"/assignments/{assignment['id']}/scores",
        judge,
        {
            "expected_revision": revision,
            "scores": [
                {"criterion_id": c, "score": s, "comment": "Helpful feedback"}
                for c, s in zip(w.criteria, values)
            ],
            "general_comment": "Good work",
        },
    )
    assert result.status_code == 200, result.text
    result = call(
        w,
        "post",
        f"/assignments/{assignment['id']}/submit",
        judge,
        {"expected_revision": revision + 1},
    )
    assert result.status_code == 200, result.text
    return result.json()


def complete(w):
    result = call(w, "post", w.base + "/assignments/auto", body={"judges_per_team": 2})
    assert result.status_code == 200, result.text
    for a in result.json()["items"]:
        judge = next(j for j in w.judges if j.id == a["judge"]["id"])
        score(w, a, judge)
    return result.json()["items"]


def test_progress_empty_round_has_null_state_and_keeps_permissions(world):
    w = world
    path = f"/events/{w.event['id']}/rounds/{w.round['id']}/judging-progress"
    assert database_query(w.engine, select(RoundJudging)) == []
    response = call(w, "get", path)
    assert response.status_code == 200
    assert response.headers["cache-control"] == "no-store"
    assert response.json() == {"items": [], "total": 0, "locked_at": None, "published_at": None}
    assert database_query(w.engine, select(RoundJudging)) == []
    for person in (w.admin, w.alice):
        assert call(w, "get", path, person).status_code == 403
    assert w.client.get("/api/v1" + path).status_code == 401


def test_rubric_validation_and_start_freeze(world):
    w = world
    base = f"/events/{w.event['id']}/rounds/{w.round['id']}/rubric"
    criterion = {"name": "Quality", "weight": 99, "max_score": 10, "order": 1}
    response = call(w, "put", base, body={"criteria": [criterion]})
    assert response.status_code == 422 and response.json()["code"] == "RUBRIC_WEIGHT_INVALID"
    criterion["weight"] = 100
    assert call(w, "put", base, w.admin, {"criteria": [criterion]}).status_code == 403
    assert call(w, "put", base, body={"criteria": [criterion]}).status_code == 200
    assert call(w, "get", base).json()["criteria"][0]["name"] == "Quality"


def test_scoring_privacy_validation_and_stale_drafts(judging_world):
    w = judging_world
    a = assign(w)["items"][0]
    path = f"/assignments/{a['id']}"
    assert a["submission_id"] == w.final["id"]
    assert a["submission_id"] != w.old_submission["id"]
    assert call(w, "get", path, w.judges[1]).status_code == 403
    assert call(w, "get", path, w.admin).status_code == 403
    detail = call(w, "get", path, w.judges[0]).json()
    assert detail["submission"]["id"] == w.final["id"]
    assert detail["submission"]["version"] == 2
    assert call(w, "get", f"/teams/{w.team['id']}", w.judges[0]).status_code == 200
    payload = {"expected_revision": 0, "scores": [{"criterion_id": w.criteria[0], "score": 11}]}
    assert (
        call(w, "put", path + "/scores", w.judges[0], payload).json()["code"]
        == "SCORE_OUT_OF_RANGE"
    )
    assert call(w, "put", path + "/scores", w.judges[1], payload).status_code == 403
    payload["scores"][0]["score"] = 8
    assert call(w, "put", path + "/scores", w.judges[0], payload).status_code == 200
    assert (
        call(w, "put", path + "/scores", w.judges[0], payload).json()["code"]
        == "SCORE_VERSION_CONFLICT"
    )
    assert (
        call(w, "post", path + "/submit", w.judges[0], {"expected_revision": 1}).json()["code"]
        == "SCORING_INCOMPLETE"
    )
    payload["expected_revision"] = 1
    payload["scores"].append(payload["scores"][0])
    assert call(w, "put", path + "/scores", w.judges[0], payload).status_code == 422
    score(w, a, w.judges[0], revision=1)
    assert (
        call(w, "put", path + "/scores", w.judges[0], payload).json()["code"]
        == "ASSIGNMENT_SUBMITTED"
    )
    assert call(w, "delete", path).status_code == 409
    assert call(w, "post", w.base + "/lock").json()["code"] == "SCORING_INCOMPLETE"


def test_lock_publish_repair_revisions_and_close(judging_world):
    w = judging_world

    def progress_state(locked, published):
        response = call(w, "get", w.base + "/judging-progress?limit=1&offset=100")
        assert response.status_code == 200, response.text
        data = response.json()
        assert data["items"] == [] and data["total"] == 1
        for field, expected in (("locked_at", locked), ("published_at", published)):
            assert bool(data[field]) is expected
            if expected:
                assert data[field].endswith("Z")
        return data

    progress_state(False, False)
    result = w.team_base + f"/rounds/{w.round['id']}/result"
    assert call(w, "post", w.base + "/lock").json()["code"] == "SCORING_INCOMPLETE"
    rows = complete(w)
    assert call(w, "get", result, w.admin).status_code == 403
    assert call(w, "post", w.base + "/lock", w.admin).status_code == 403
    assert call(w, "post", w.base + "/lock").status_code == 204
    locked = progress_state(True, False)["locked_at"]
    assert call(w, "get", result, w.admin).json()["total"] == "78.00"
    assert call(w, "get", result, w.alice).json()["code"] == "NOT_PUBLISHED"
    assert w.client.get("/api/v1" + w.base + "/leaderboard").status_code == 409
    assert call(w, "post", w.base + "/publish").status_code == 204
    assert progress_state(True, True)["locked_at"] == locked
    assert call(w, "post", w.base + "/publish").status_code == 204
    board = w.client.get("/api/v1" + w.base + "/leaderboard").json()
    assert board["publication_revision"] == 1 and board["total"] == 1
    assert "judge" not in str(board) and "@example.com" not in str(board)
    assert call(w, "get", result, w.alice).json()["comments"]
    assert (
        call(w, "post", w.base + "/unlock", body={"reason": "correction"}).json()["code"]
        == "RESULTS_PUBLISHED"
    )
    assert call(w, "post", w.base + "/unpublish", body={"reason": "correction"}).status_code == 204
    assert progress_state(True, False)["locked_at"] == locked
    assert w.client.get("/api/v1" + w.base + "/leaderboard").status_code == 409
    assert call(w, "post", w.base + "/unlock", body={"reason": "correction"}).status_code == 204
    progress_state(False, False)
    a = rows[0]
    judge = next(j for j in w.judges if j.id == a["judge"]["id"])
    reopened = call(w, "post", f"/assignments/{a['id']}/reopen", body={"reason": "fix"}).json()
    score(w, a, judge, values=(10, 20), revision=reopened["revision"])
    assert call(w, "post", w.base + "/lock").status_code == 204
    assert call(w, "post", w.base + "/publish").status_code == 204
    assert call(w, "get", result, w.alice).json()["total"] == "89.00"
    assert call(w, "get", result, w.alice).json()["publication_revision"] == 2
    progress_state(True, True)
    snapshots = database_query(w.engine, select(PublicationSnapshot))
    assert len(snapshots) == 2
    assert len(database_query(w.engine, select(ResultEmail))) == 2
    actions = database_query(w.engine, select(AuditLog.action))
    assert "round.unpublish" in actions and "assignment.reopen" in actions
    database_query(
        w.engine, update(Event).where(Event.id == UUID(w.event["id"])).values(status="judging")
    )
    assert (
        call(
            w, "post", f"/events/{w.event['id']}/transition", body={"to_status": "closed"}
        ).status_code
        == 200
    )
    assert call(w, "post", w.base + "/unpublish", body={"reason": "too late"}).status_code == 409


def test_late_conflict_cancel_reassign_and_history(judging_world):
    w = judging_world
    rows = complete(w)
    a = rows[0]
    judge = next(j for j in w.judges if j.id == a["judge"]["id"])
    response = call(
        w,
        "post",
        f"/events/{w.event['id']}/conflicts",
        judge,
        {"team_id": w.team["id"], "reason": "Worked with this team"},
    )
    assert response.status_code == 201
    assert call(w, "post", w.base + "/lock").json()["code"] == "SCORING_INCOMPLETE"
    assert (
        call(
            w, "post", f"/assignments/{a['id']}/cancel", body={"reason": "replace judge"}
        ).status_code
        == 200
    )
    assert call(w, "get", f"/events/{w.event['id']}/conflicts", w.alice).status_code == 403
    new = call(w, "post", w.base + "/assignments/auto", body={"judges_per_team": 2}).json()
    assert len(new["items"]) == 1 and new["unfilled"] == []
    replacement = new["items"][0]
    assert replacement["judge"]["id"] != judge.id
    assert call(w, "get", f"/assignments/{a['id']}").json()["scores"]


def test_mentoring_qa_revocation_and_conflicts(judging_world):
    w = judging_world
    base = f"/events/{w.event['id']}/mentor-assignments"
    data = {"mentor_id": w.mentor.id, "team_ids": [w.team["id"]]}
    assert call(w, "post", base, w.admin, data).status_code == 403
    assigned = call(w, "post", base, body=data).json()["items"][0]
    assert call(w, "post", base, body=data).json()["items"] == []
    assert call(w, "get", "/me/mentoring", w.mentor).json()["total"] == 1
    assert (
        call(w, "delete", f"/events/{w.event['id']}/roles/{w.mentor_role['id']}").json()["code"]
        == "ROLE_IN_USE"
    )
    note = {"content": "  Focus on validation  ", "kind": "progress", "progress_status": "on_track"}
    assert call(w, "post", w.team_base + "/mentor-notes", w.mentor, note).status_code == 201
    assert (
        call(
            w,
            "post",
            w.team_base + "/mentor-notes",
            w.mentor,
            {"content": "x", "commit_sha": "a" * 40},
        ).json()["code"]
        == "COMMIT_NOT_FOUND"
    )
    question = call(
        w,
        "post",
        w.team_base + "/questions",
        w.alice,
        {"title": " Need help ", "content": " How to test? "},
    ).json()
    assert question["title"] == "Need help"
    qpath = f"/questions/{question['id']}"
    assert call(w, "post", qpath + "/answers", w.judges[0], {"content": "x"}).status_code == 403
    assert (
        call(w, "post", qpath + "/answers", w.mentor, {"content": "Use boundary tests"}).status_code
        == 201
    )
    assert (
        call(w, "get", w.team_base + "/questions", w.alice).json()["items"][0]["status"]
        == "answered"
    )
    assert call(w, "post", qpath + "/resolve", w.alice).status_code == 204
    assert call(w, "post", qpath + "/resolve", w.alice).status_code == 204
    assert (
        call(w, "post", qpath + "/answers", w.mentor, {"content": "x"}).json()["code"]
        == "QUESTION_RESOLVED"
    )
    assert call(w, "delete", f"/mentor-assignments/{assigned['id']}").status_code == 204
    assert call(w, "get", w.team_base + "/questions", w.mentor).status_code == 403
    assert (
        call(w, "get", w.team_base + f"/rounds/{w.round['id']}/submissions", w.mentor).status_code
        == 403
    )
    assert call(w, "get", qpath + "/answers", w.admin).json()["total"] == 1
    grant(w, w.mentor, "judge")
    assert assign(w, w.mentor)["skipped"][0]["code"] == "CONFLICT_OF_INTEREST"


def test_round_scope_and_admin_mutations(judging_world):
    w = judging_world
    assert call(w, "get", "/me/assignments", w.alice).status_code == 403
    assert call(w, "get", "/me/mentoring", w.alice).status_code == 403
    for suffix, method, body in [
        ("/assignments", "post", {"judge_id": w.judges[0].id, "team_ids": [w.team["id"]]}),
        ("/lock", "post", None),
        ("/publish", "post", None),
    ]:
        assert call(w, method, w.base + suffix, w.admin, body).status_code == 403
    wrong = f"/events/{uuid4()}/rounds/{w.round['id']}/rubric"
    assert call(w, "get", wrong).status_code == 404
    wrong = f"/events/{w.event['id']}/rounds/{uuid4()}/rubric"
    assert call(w, "get", wrong).status_code == 404
    assert (
        call(w, "post", w.base + "/assignments/auto", body={"judges_per_team": 1}).status_code
        == 422
    )
    from tests.test_events_teams import event_input

    other = call(w, "post", "/events", w.admin, event_input(w.organizer, "other-event")).json()
    cross = f"/events/{other['id']}/rounds/{w.round['id']}"
    assert call(w, "get", cross + "/rubric", w.admin).status_code == 404
    assert (
        call(
            w,
            "post",
            cross + "/assignments",
            body={"judge_id": w.judges[0].id, "team_ids": [w.team["id"]]},
        ).status_code
        == 404
    )
    assert (
        call(
            w,
            "post",
            f"/events/{other['id']}/mentor-assignments",
            body={"mentor_id": w.mentor.id, "team_ids": [w.team["id"]]},
        ).status_code
        == 409
    )


def test_decimal_ranking_ties_tracks_and_rounding():
    c = SimpleNamespace(
        id=uuid4(), name="Quality", weight=Decimal(100), max_score=Decimal(3), order=1
    )
    teams = [
        SimpleNamespace(id=uuid4(), name=f"T{i}", track_id=uuid4() if i == 2 else None)
        for i in range(3)
    ]
    assignments = [
        SimpleNamespace(id=uuid4(), team_id=t.id, status="submitted", general_comment=None)
        for t in teams
    ]
    scores = [
        SimpleNamespace(
            assignment_id=a.id, criterion_id=c.id, score=Decimal(2 if i < 2 else 1), comment=None
        )
        for i, a in enumerate(assignments)
    ]
    submissions = {t.id: SimpleNamespace(submitted_at=datetime(2026, 1, 1)) for t in teams}
    data = calculate(teams, submissions, assignments, scores, [c])
    rows = data["boards"]["all"]
    assert [r["rank"] for r in rows] == [1, 1, 3]
    assert [r["tied"] for r in rows] == [True, True, False]
    assert rows[0]["total"] == "66.67"
    assert data["boards"][str(teams[2].track_id)][0]["rank"] == 1
    sample = [
        {
            "team": {"id": "a"},
            "total": "50.00",
            "criteria": [{"criterion_id": str(c.id), "avg": "1"}],
            "submitted_at": "2026-01-02",
        },
        {
            "team": {"id": "b"},
            "total": "50.00",
            "criteria": [{"criterion_id": str(c.id), "avg": "1.01"}],
            "submitted_at": "2026-01-03",
        },
    ]
    assert rank_rows(sample, [c])[0]["team"]["id"] == "b"


def test_eligibility_source_publication_and_submission_guard(judging_world):
    w = judging_world
    complete(w)
    assert call(w, "post", w.base + "/lock").status_code == 204
    assert call(w, "post", w.base + "/publish").status_code == 204
    second = uuid4()

    async def add_round():
        async with async_sessionmaker(w.engine)() as session:
            session.add(
                Round(
                    id=second,
                    event_id=UUID(w.event["id"]),
                    name="Final",
                    order=2,
                    starts_at=w.now + timedelta(hours=1),
                    submission_deadline=w.now + timedelta(hours=2),
                    ends_at=w.now + timedelta(days=1),
                )
            )
            await session.commit()

    asyncio.run(add_round())
    path = f"/events/{w.event['id']}/rounds/{second}/eligible-teams"
    payload = {"source_round_id": w.round["id"], "team_ids": [w.team["id"]]}
    assert call(w, "get", path).json()["total"] == 0
    assert call(w, "put", path, body={**payload, "source_round_id": str(second)}).status_code == 409
    assert call(w, "put", path, body=payload).json()["total"] == 1
    assert call(w, "post", w.base + "/unpublish", body={"reason": "review"}).status_code == 204
    assert call(w, "get", path).json()["total"] == 1
    from app.modules.events.repository import EventRepository
    from app.modules.events.service import EventService
    from app.modules.judging.repository import JudgingRepository
    from app.modules.judging.service import JudgingService

    async def eligible():
        async with async_sessionmaker(w.engine)() as session:
            events = EventService(
                EventRepository(session), None, JudgingService(JudgingRepository(session))
            )
            round_ = await events.submission_round(UUID(w.event["id"]), second)
            return await events.submission_eligible(round_, UUID(w.team["id"]))

    assert not asyncio.run(eligible())
    assert call(w, "post", w.base + "/publish").status_code == 204
    assert asyncio.run(eligible())
    database_query(
        w.engine,
        update(Round).where(Round.id == second).values(starts_at=w.now - timedelta(minutes=1)),
    )
    assert call(w, "put", path, body=payload).json()["code"] == "ROUND_ALREADY_STARTED"
    assert call(w, "post", w.base + "/unpublish", body={"reason": "review"}).status_code == 409


def test_result_worker_receipts_are_idempotent_and_failures_not_retried(judging_world, monkeypatch):
    from unittest.mock import Mock

    from sqlalchemy import create_engine
    from sqlalchemy.orm import Session

    from app.integrations import mailer
    from app.modules.judging.jobs import ResultEmailJobs
    from app.modules.judging.repository import ResultEmailRepository

    w = judging_world
    complete(w)
    call(w, "post", w.base + "/lock")
    call(w, "post", w.base + "/publish")
    url = (
        w.engine.url.render_as_string(hide_password=False)
        .replace("sqlite+aiosqlite:", "sqlite:")
        .replace("postgresql+asyncpg:", "postgresql+psycopg:")
    )
    engine = create_engine(url)
    send = Mock()
    monkeypatch.setattr(mailer, "send_email", send)
    try:
        with Session(engine, expire_on_commit=False) as session:
            jobs = ResultEmailJobs(ResultEmailRepository(session))
            assert jobs.deliver() == 1
            assert jobs.deliver() == 0
            assert send.call_count == 1
        call(w, "post", w.base + "/unpublish", body={"reason": "update"})
        call(w, "post", w.base + "/publish")
        send.side_effect = RuntimeError("ambiguous SMTP delivery")
        with Session(engine, expire_on_commit=False) as session:
            jobs = ResultEmailJobs(ResultEmailRepository(session))
            assert jobs.deliver() == 0
            assert jobs.deliver() == 0
        assert send.call_count == 2
        statuses = database_query(w.engine, select(ResultEmail.status))
        assert sorted(statuses) == ["accepted", "failed"]
    finally:
        engine.dispose()


def test_concurrent_draft_revision_has_one_winner(judging_world):
    w = judging_world
    if w.engine.dialect.name != "postgresql":
        pytest.skip("Row-lock behavior requires PostgreSQL")
    a = assign(w)["items"][0]
    payload = {"expected_revision": 0, "scores": [{"criterion_id": w.criteria[0], "score": 5}]}

    def save():
        return call(w, "put", f"/assignments/{a['id']}/scores", w.judges[0], payload)

    with ThreadPoolExecutor(max_workers=2) as pool:
        responses = list(pool.map(lambda _: save(), range(2)))
    assert sorted(r.status_code for r in responses) == [200, 409]
    assert (
        next(r for r in responses if r.status_code == 409).json()["code"]
        == "SCORE_VERSION_CONFLICT"
    )


def test_auto_underfilled_repeat_and_unsubmitted_progress(judging_world):
    w = judging_world
    for judge in w.judges[:2]:
        response = call(
            w,
            "post",
            f"/events/{w.event['id']}/conflicts",
            judge,
            {"team_id": w.team["id"], "reason": "Prior collaboration"},
        )
        assert response.status_code == 201
    first = call(w, "post", w.base + "/assignments/auto", body={"judges_per_team": 2}).json()
    assert len(first["items"]) == 1 and first["unfilled"][0]["missing_judges"] == 1
    second = call(w, "post", w.base + "/assignments/auto", body={"judges_per_team": 2}).json()
    assert second["items"] == [] and second["unfilled"][0]["missing_judges"] == 1
    a = first["items"][0]
    assert call(w, "delete", f"/assignments/{a['id']}").status_code == 204
    from app.modules.submissions.models import Submission

    database_query(w.engine, update(Submission).values(submitted_at=w.now + timedelta(hours=1)))
    assert (
        call(w, "get", w.base + "/judging-progress").json()["items"][0]["status"] == "not_submitted"
    )
    assert call(w, "post", w.base + "/lock").json()["code"] == "SCORING_INCOMPLETE"


def test_qa_rate_limit_pending_members_and_state(judging_world):
    from app.modules.teams.models import TeamMember

    w = judging_world
    w.limiter.return_value = False
    response = call(
        w, "post", w.team_base + "/questions", w.alice, {"title": "Help", "content": "Please"}
    )
    assert response.status_code == 429
    w.limiter.return_value = True
    database_query(
        w.engine,
        update(TeamMember).where(TeamMember.user_id == UUID(w.alice.id)).values(status="pending"),
    )
    assert call(w, "get", w.team_base + "/questions", w.alice).status_code == 403
    assert (
        call(
            w, "post", w.team_base + "/questions", w.alice, {"title": "Help", "content": "Please"}
        ).status_code
        == 403
    )
    database_query(
        w.engine,
        update(TeamMember).where(TeamMember.user_id == UUID(w.alice.id)).values(status="active"),
    )
    database_query(
        w.engine, update(Event).where(Event.id == UUID(w.event["id"])).values(status="judging")
    )
    assert (
        call(
            w, "post", w.team_base + "/questions", w.alice, {"title": "Help", "content": "Please"}
        ).status_code
        == 409
    )
