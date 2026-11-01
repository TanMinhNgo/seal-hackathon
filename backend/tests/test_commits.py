from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from unittest.mock import Mock
from uuid import UUID, uuid4

import httpx
import pytest
from celery.exceptions import Retry
from pydantic import SecretStr
from sqlalchemy import create_engine, update
from sqlalchemy.orm import Session

from app.integrations import github_sync
from app.integrations.github_sync import GitHubSync, GitHubSyncError
from app.modules.auth.models import AuditLog
from app.modules.commits import jobs
from app.modules.commits.jobs import CommitJobs
from app.modules.commits.models import CommitSyncState
from app.modules.commits.repository import CommitJobRepository
from app.modules.events.models import Event
from app.modules.teams.models import TeamMember
from tests.test_auth import database_query
from tests.test_events_teams import account
from worker.tasks import commits as tasks

A, B, C = (letter * 40 for letter in "abc")


def call(w, path, person=None, method="get", body=None):
    return getattr(w.client, method)(
        "/api/v1" + path,
        headers=(person or w.organizer).headers,
        **({"json": body} if body else {}),
    )


@pytest.fixture
def commit_world(submission_world, auth_settings, monkeypatch):
    w = submission_world
    url = w.engine.url.set(
        drivername="sqlite"
        if w.engine.url.drivername.startswith("sqlite")
        else "postgresql+psycopg"
    )
    engine = create_engine(url)
    w.sync_engine = engine
    w.settings = auth_settings
    w.base = f"/teams/{w.team['id']}"
    fake = Mock()
    fake.branch_head.return_value = ("main", A)
    fake.history.return_value = ([A], True)
    fake.detail.side_effect = lambda sha, heartbeat: {
        "sha": sha,
        "author": "Student",
        "message": "<script>plain text</script>",
        "committed_at": datetime.now(UTC) - timedelta(days=100),
        "additions": 3,
        "deletions": 1,
        "url": f"https://github.com/example/public/commit/{sha}",
        "files": [
            {
                "path": "main.py",
                "previous_path": None,
                "status": "modified",
                "additions": 3,
                "deletions": 1,
                "patch": "+hello",
                "binary": False,
                "truncated": False,
            }
        ],
        "diff_truncated": False,
    }
    w.github = fake
    monkeypatch.setattr(jobs, "GitHubSync", Mock(return_value=fake))
    w.publish = Mock()
    monkeypatch.setattr(tasks.sync_team, "apply_async", w.publish)
    try:
        yield w
    finally:
        engine.dispose()


def run(w, *, complete=True, shas=None):
    w.github.history.return_value = (shas or [A], complete)
    token = str(uuid4())
    with Session(w.sync_engine, expire_on_commit=False) as session:
        repo = CommitJobRepository(session)
        assert repo.claim(UUID(w.team["id"]), token, 0)
        return CommitJobs(repo, w.settings).run(UUID(w.team["id"]), token)


def test_baseline_late_push_rewrite_incomplete_and_idempotency(commit_world):
    w = commit_world
    assert run(w)
    assert run(w)
    assert call(w, w.base + "/commits").json()["total"] == 1
    assert call(w, w.base + "/commits/" + A).json()["baseline"] is True
    w.github.branch_head.return_value = ("main", B)
    assert run(w, shas=[B, A])
    late = call(w, w.base + "/commits/" + B).json()
    assert late["in_event_window"] and not late["baseline"]
    assert datetime.fromisoformat(late["committed_at"]) < datetime.now(UTC) - timedelta(days=90)
    stats = call(w, w.base + "/commit-stats").json()
    assert stats["total"] == 1 and stats["sync_status"] == "ok"
    assert not run(w, shas=[B], complete=False)
    assert not call(w, w.base + "/commits/" + A).json()["removed"]
    assert call(w, w.base + "/commit-stats").json()["last_synced_at"] == stats["last_synced_at"]
    assert run(w, shas=[B])
    assert call(w, w.base + "/commits/" + A).json()["removed"]
    assert run(w, shas=[B, A])
    assert not call(w, w.base + "/commits/" + A).json()["removed"]


def test_access_diff_pagination_and_pending_member(commit_world):
    w = commit_world
    run(w)
    outsider = account(w.client, w.engine, "outsider")
    for suffix in ["/commits", "/commits/" + A, "/commits/" + A + "/diff", "/commit-stats"]:
        assert call(w, w.base + suffix, outsider).status_code == 403
        response = call(w, w.base + suffix, w.admin)
        assert response.status_code == 200, response.text
        assert response.headers["cache-control"] == "no-store"
        assert call(w, w.base + suffix, w.alice).status_code == 200
    diff = call(w, w.base + f"/commits/{A}/diff?limit=1&offset=1").json()
    assert diff == {"items": [], "total": 1, "truncated": False}
    assert call(w, w.base + "/commits/" + C).status_code == 404
    assert call(w, w.base + "/commits/not-a-sha").status_code == 422
    database_query(w.engine, update(TeamMember).values(status="pending"))
    assert call(w, w.base + "/commits", w.alice).status_code == 403


def test_manual_sync_lease_cooldown_queue_error_and_closed(commit_world):
    w = commit_world
    assert call(w, w.base + "/sync", w.admin, "post").status_code == 403
    response = call(w, w.base + "/sync", method="post")
    assert response.status_code == 202, response.text
    assert call(w, w.base + "/sync", method="post").json()["code"] == "SYNC_IN_PROGRESS"
    database_query(w.engine, update(CommitSyncState).values(lease_until=None, lease_token=None))
    assert call(w, w.base + "/sync", method="post").status_code == 429
    database_query(
        w.engine,
        update(CommitSyncState).values(last_attempt_at=datetime.now(UTC) - timedelta(minutes=2)),
    )
    w.publish.side_effect = ConnectionError("sensitive transport error")
    response = call(w, w.base + "/sync", method="post")
    assert response.status_code == 503 and "sensitive" not in response.text
    assert call(w, w.base + "/commit-stats").json()["running"]
    database_query(w.engine, update(Event).values(status="closed"))
    assert call(w, w.base + "/sync", method="post").status_code == 409


def test_worker_lease_duplicate_recovery_closed_and_error_safety(commit_world):
    w = commit_world
    with Session(w.sync_engine, expire_on_commit=False) as session:
        repo = CommitJobRepository(session)
        token = str(uuid4())
        assert repo.claim(UUID(w.team["id"]), token, 0)
        assert not repo.claim(UUID(w.team["id"]), str(uuid4()), 0)
        worker = CommitJobs(repo, w.settings)
        assert worker.run(UUID(w.team["id"]), token)
        assert not worker.run(UUID(w.team["id"]), token)
    w.github.history.side_effect = GitHubSyncError("GITHUB_RATE_LIMITED")
    with pytest.raises(GitHubSyncError):
        run(w)
    stats = call(w, w.base + "/commit-stats").json()
    assert stats["sync_error"] == "GITHUB_RATE_LIMITED" and not stats["running"]
    database_query(w.engine, update(Event).values(status="closed"))
    assert run(w) is False
    assert call(w, w.base + "/commits", w.admin).json()["total"] == 1


def test_overview_inactivity_errors_and_config(commit_world):
    w = commit_world
    path = f"/events/{w.event['id']}"
    response = call(
        w, path, method="patch", body={"sync_interval_minutes": 1, "inactivity_alert_hours": 1}
    )
    assert response.status_code == 200, response.text
    assert call(w, path, w.admin, "patch", {"sync_interval_minutes": 2}).status_code == 403
    assert call(w, path, method="patch", body={"sync_interval_minutes": 0}).status_code == 422
    run(w)
    overview = call(w, path + "/commit-overview").json()
    assert overview["total"] == 1 and overview["items"][0]["inactive"]
    with Session(w.sync_engine) as session:
        session.add(
            AuditLog(
                actor_id=UUID(w.organizer.id),
                action="event.transitioned",
                target_type="event",
                target_id=w.event["id"],
                data={"before": "open", "after": "ongoing"},
            )
        )
        session.commit()
    assert not call(w, path + "/commit-overview").json()["items"][0]["inactive"]
    database_query(
        w.engine,
        update(CommitSyncState).values(sync_status="error", sync_error="REPO_NOT_ACCESSIBLE"),
    )
    assert not call(w, path + "/commit-overview").json()["items"][0]["inactive"]
    assert call(w, path + "/commit-overview", w.admin).status_code == 403


def test_repo_failure_alert_once_then_recovery(commit_world, monkeypatch):
    w = commit_world
    send = Mock(side_effect=ConnectionError("ambiguous SMTP"))
    monkeypatch.setattr(jobs.mailer, "send_email", send)
    w.github.branch_head.side_effect = GitHubSyncError("REPO_NOT_ACCESSIBLE")
    for _ in range(2):
        with pytest.raises(GitHubSyncError):
            run(w)
    assert send.call_count == 1
    w.github.branch_head.side_effect = None
    assert run(w)
    w.github.branch_head.side_effect = GitHubSyncError("REPO_NOT_ACCESSIBLE")
    with pytest.raises(GitHubSyncError):
        run(w)
    assert send.call_count == 2


@pytest.fixture
def github(auth_settings, monkeypatch):
    auth_settings.github_token = SecretStr("test-token")
    monkeypatch.setattr(github_sync, "budget_pause", lambda settings: 0)
    redis = Mock()
    redis.__enter__ = Mock(return_value=redis)
    redis.__exit__ = Mock(return_value=False)
    monkeypatch.setattr(github_sync.Redis, "from_url", Mock(return_value=redis))
    client = GitHubSync(auth_settings, "https://github.com/example/public")
    client.client.close()
    yield client, redis
    client.close()


def transport(client, handler):
    client.client = httpx.Client(
        base_url="https://api.github.com", transport=httpx.MockTransport(handler)
    )


def test_github_pagination_pins_head_and_does_not_filter_since(github):
    client, _ = github
    requests = []

    def handle(request):
        requests.append(request)
        page = int(request.url.params["page"])
        return httpx.Response(
            200,
            json=[{"sha": A if page == 1 else B, "parents": [{"sha": B}] if page == 1 else []}],
            headers={"link": '<https://api.github.com/next>; rel="next"'} if page == 1 else {},
        )

    transport(client, handle)
    assert client.history(A, lambda: None) == ([A, B], True)
    assert all(r.url.params["sha"] == A and "since" not in r.url.params for r in requests)


def test_github_history_bound_and_empty_page_are_not_complete(github):
    client, _ = github
    transport(
        client,
        lambda request: httpx.Response(
            200,
            json=[{"sha": A, "parents": []}],
            headers={"link": '<https://api.github.com/next>; rel="next"'},
        ),
    )
    assert client.history(A, lambda: None)[1] is False
    transport(
        client,
        lambda request: httpx.Response(
            200, json=[], headers={"link": '<https://api.github.com/next>; rel="next"'}
        ),
    )
    with pytest.raises(GitHubSyncError, match="GITHUB_INCOMPLETE_HISTORY"):
        client.history(A, lambda: None)
    transport(
        client, lambda request: httpx.Response(200, json=[{"sha": A, "parents": [{"sha": B}]}])
    )
    assert client.history(A, lambda: None) == ([A], False)


def test_github_keeps_fixed_branch_when_default_changes(github):
    client, _ = github
    paths = []

    def handle(request):
        paths.append(request.url.path)
        return httpx.Response(
            200,
            json={"sha": A}
            if "/commits/" in request.url.path
            else {"private": False, "default_branch": "new-default"},
        )

    transport(client, handle)
    assert client.branch_head("original/branch") == ("original/branch", A)
    assert paths[-1].endswith("/commits/original/branch")


def test_github_diff_limits_missing_patch_and_renames(github, monkeypatch):
    client, _ = github
    monkeypatch.setattr(github_sync, "MAX_PATCH_BYTES", 4)
    monkeypatch.setattr(github_sync, "MAX_FILES", 2)

    def handle(request):
        return httpx.Response(
            200,
            json={
                "sha": A,
                "commit": {
                    "author": {"name": "Student"},
                    "message": "hello",
                    "committer": {"date": "2026-01-01T00:00:00Z"},
                },
                "stats": {"additions": 9, "deletions": 1},
                "files": [
                    {
                        "filename": "new.py",
                        "previous_filename": "old.py",
                        "status": "renamed",
                        "additions": 9,
                        "deletions": 1,
                        "patch": "ééé",
                    },
                    {"filename": "image.png", "status": "added", "additions": 0, "deletions": 0},
                    {"filename": "other.py", "status": "added", "additions": 1, "deletions": 0},
                ],
            },
        )

    transport(client, handle)
    result = client.detail(A, lambda: None)
    assert result["diff_truncated"] and len(result["files"]) == 2
    assert result["files"][0]["patch"] == "éé"
    assert result["files"][0]["previous_path"] == "old.py"
    assert result["files"][1]["binary"] is None and result["files"][1]["truncated"]


@pytest.mark.parametrize(
    "status,headers",
    [(200, {"x-ratelimit-remaining": "10"}), (429, {}), (403, {"retry-after": "120"})],
)
def test_github_rate_limit_shared_pause(github, status, headers):
    client, redis = github
    transport(client, lambda request: httpx.Response(status, json={}, headers=headers))
    with pytest.raises(GitHubSyncError, match="GITHUB_RATE_LIMITED"):
        client.get()
    assert redis.set.call_args.args[0] == github_sync.RATE_KEY


def test_dispatch_isolates_queue_errors_and_respects_interval(commit_world, monkeypatch):
    w = commit_world
    monkeypatch.setattr(
        tasks, "sync_session_factory", lambda: Session(w.sync_engine, expire_on_commit=False)
    )
    monkeypatch.setattr(tasks, "budget_pause", lambda settings: 0)
    monkeypatch.setattr(tasks, "get_settings", lambda: w.settings)
    w.publish.side_effect = ConnectionError()
    assert tasks.sync_commits() == 0
    assert call(w, w.base + "/commit-stats").json()["sync_error"] == "SYNC_QUEUE_UNAVAILABLE"
    w.publish.side_effect = None
    assert tasks.sync_commits() == 0
    database_query(
        w.engine,
        update(CommitSyncState).values(last_attempt_at=datetime.now(UTC) - timedelta(hours=1)),
    )
    assert tasks.sync_commits() == 1
    assert tasks.sync_commits() == 0


def test_mentor_commit_link_and_revocation(commit_world):
    w = commit_world
    run(w)
    mentor = account(w.client, w.engine, "mentor-phase5")
    event_path = f"/events/{w.event['id']}"
    response = call(
        w, event_path + "/roles", method="post", body={"email": mentor.email, "role": "mentor"}
    )
    assert response.status_code == 201, response.text
    response = call(
        w,
        event_path + "/mentor-assignments",
        method="post",
        body={"mentor_id": mentor.id, "team_ids": [w.team["id"]]},
    )
    assert response.status_code == 201, response.text
    assignment = response.json()["items"][0]
    assert call(w, w.base + "/commits/" + A + "/diff", mentor).status_code == 200
    response = call(
        w,
        w.base + "/mentor-notes",
        mentor,
        "post",
        {"content": "Check this commit", "commit_sha": A},
    )
    assert response.status_code == 201, response.text
    assert (
        call(
            w,
            w.base + "/mentor-notes",
            mentor,
            "post",
            {"content": "Unknown commit", "commit_sha": C},
        ).json()["code"]
        == "COMMIT_NOT_FOUND"
    )
    response = call(
        w,
        w.base + "/questions",
        w.alice,
        "post",
        {"title": "Help with commit", "content": "Please review this", "commit_sha": A},
    )
    assert response.status_code == 201, response.text
    assert call(w, "/mentor-assignments/" + assignment["id"], method="delete").status_code == 204
    assert call(w, w.base + "/commits/" + A + "/diff", mentor).status_code == 403


def test_task_retry_reserves_one_lease_and_stops_at_limit(commit_world, monkeypatch):
    w = commit_world
    monkeypatch.setattr(
        tasks, "sync_session_factory", lambda: Session(w.sync_engine, expire_on_commit=False)
    )
    monkeypatch.setattr(tasks, "get_settings", lambda: w.settings)
    retry = Mock(return_value=Retry())
    monkeypatch.setattr(tasks.sync_team, "retry", retry)
    w.github.history.side_effect = GitHubSyncError("GITHUB_RATE_LIMITED", 120)
    with Session(w.sync_engine, expire_on_commit=False) as session:
        token = str(uuid4())
        assert CommitJobRepository(session).claim(UUID(w.team["id"]), token, 0)
    with pytest.raises(Retry):
        tasks.sync_team.run(w.team["id"], token)
    assert retry.call_args.kwargs["countdown"] == 120
    assert call(w, w.base + "/commit-stats").json()["running"]
    assert tasks.sync_team.run(w.team["id"], token) is False


def test_expired_lease_recovers_without_waiting_event_interval(commit_world):
    w = commit_world
    with Session(w.sync_engine, expire_on_commit=False) as session:
        repo = CommitJobRepository(session)
        assert repo.claim(UUID(w.team["id"]), str(uuid4()), 0)
    database_query(
        w.engine,
        update(CommitSyncState).values(lease_until=datetime.now(UTC) - timedelta(seconds=1)),
    )
    assert call(w, w.base + "/commit-stats").json()["sync_error"] == "SYNC_WORKER_TIMEOUT"
    with Session(w.sync_engine, expire_on_commit=False) as session:
        assert CommitJobRepository(session).claim(UUID(w.team["id"]), str(uuid4()), 30)


def test_concurrent_claims_only_one_owner(commit_world):
    w = commit_world

    def claim():
        with Session(w.sync_engine, expire_on_commit=False) as session:
            return CommitJobRepository(session).claim(UUID(w.team["id"]), str(uuid4()), 0)

    with ThreadPoolExecutor(max_workers=2) as pool:
        assert sorted(pool.map(lambda _: claim(), range(2))) == [False, True]


def test_worker_cannot_write_after_lease_replacement_or_event_stop(commit_world):
    w = commit_world
    original = w.github.detail.side_effect

    def stop(sha, heartbeat):
        database_query(w.engine, update(Event).values(status="judging"))
        return original(sha, heartbeat)

    w.github.detail.side_effect = stop
    assert run(w) is False
    assert call(w, w.base + "/commits").json()["total"] == 0
    database_query(w.engine, update(Event).values(status="ongoing"))

    def steal(sha, heartbeat):
        database_query(w.engine, update(CommitSyncState).values(lease_token="replacement"))
        return original(sha, heartbeat)

    w.github.detail.side_effect = steal
    assert run(w) is False
    assert call(w, w.base + "/commits").json()["total"] == 0


def test_dispatch_continues_after_one_team_enqueue_failure(monkeypatch):
    session = Mock()
    factory = Mock()
    factory.__enter__ = Mock(return_value=session)
    factory.__exit__ = Mock(return_value=False)
    repository = Mock()
    repository.claim.return_value = True
    event = Mock(sync_interval_minutes=30)
    teams = [Mock(id=uuid4()), Mock(id=uuid4())]
    dispatcher = Mock()
    dispatcher.contexts.return_value = [(event, team) for team in teams]
    publish = Mock(side_effect=[ConnectionError(), None])
    monkeypatch.setattr(tasks, "sync_session_factory", lambda: factory)
    monkeypatch.setattr(tasks, "budget_pause", lambda settings: 0)
    monkeypatch.setattr(tasks, "CommitJobRepository", Mock(return_value=repository))
    monkeypatch.setattr(tasks, "CommitJobs", Mock(return_value=dispatcher))
    monkeypatch.setattr(tasks.sync_team, "apply_async", publish)
    assert tasks.sync_commits() == 1
    assert publish.call_count == 2 and repository.release.call_count == 1
