import asyncio
import os
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from time import perf_counter
from uuid import UUID, uuid4

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.core.security import issue_tokens, token_hash
from app.modules.auth.models import EventRole, RefreshSession, User
from app.modules.submissions.models import Submission
from app.modules.teams.models import Team, TeamMember
from tests.test_auth import database_query


@pytest.mark.skipif(os.environ.get("SEAL_RUN_LOAD") != "1", reason="Explicit PostgreSQL load run")
def test_100_teams_submit_and_replay_in_one_minute(
    submission_world, auth_settings, record_property
):
    w = submission_world
    if w.engine.dialect.name != "postgresql":
        pytest.skip("Load verification requires dedicated PostgreSQL")

    async def prepare():
        fixtures = [(w.path, w.alice.headers)]
        async with async_sessionmaker(w.engine, expire_on_commit=False)() as session:
            for number in range(1, 100):
                user_id, team_id, session_id = uuid4(), uuid4(), uuid4()
                access, refresh, expires = issue_tokens(auth_settings, user_id, session_id)
                session.add(
                    User(
                        id=user_id,
                        email=f"load-{number:03}@example.com",
                        full_name=f"Load participant {number:03}",
                        password_hash="unused-load-fixture",
                        email_verified=True,
                        is_active=True,
                    )
                )
                await session.flush()
                session.add_all(
                    [
                        EventRole(
                            user_id=user_id, event_id=UUID(w.event["id"]), role="participant"
                        ),
                        RefreshSession(
                            id=session_id,
                            user_id=user_id,
                            token_hash=token_hash(refresh),
                            expires_at=expires,
                        ),
                        Team(
                            id=team_id,
                            event_id=UUID(w.event["id"]),
                            leader_id=user_id,
                            name=f"Load team {number:03}",
                            status="approved",
                            repo_url=w.body["repo_url"],
                        ),
                    ]
                )
                await session.flush()
                session.add(
                    TeamMember(
                        team_id=team_id,
                        event_id=UUID(w.event["id"]),
                        user_id=user_id,
                        status="active",
                        joined_at=datetime.now(UTC),
                    )
                )
                fixtures.append(
                    (
                        f"/api/v1/teams/{team_id}/rounds/{w.round['id']}/submissions",
                        {"Authorization": f"Bearer {access}"},
                    )
                )
            await session.commit()
        return fixtures

    fixtures = asyncio.run(prepare())

    def submit(item):
        index, (path, headers) = item
        headers = {**headers, "Idempotency-Key": f"phase7-load-{index:03}"}
        before = perf_counter()
        first = w.client.post(path, headers=headers, json=w.body)
        replay = w.client.post(path, headers=headers, json=w.body)
        assert first.status_code == replay.status_code == 201
        assert first.json()["id"] == replay.json()["id"]
        assert first.json()["version"] == replay.json()["version"] == 1
        return first.json()["id"], perf_counter() - before

    before = perf_counter()
    with ThreadPoolExecutor(max_workers=20) as pool:
        results = list(pool.map(submit, enumerate(fixtures)))
    elapsed = perf_counter() - before
    assert len({result[0] for result in results}) == 100
    assert database_query(w.engine, select(func.count()).select_from(Submission))[0] == 100
    assert elapsed < 60
    record_property("elapsed_seconds", round(elapsed, 3))
    record_property(
        "p95_with_replay_seconds", round(sorted(result[1] for result in results)[94], 3)
    )
