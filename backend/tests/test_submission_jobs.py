import asyncio
from datetime import timedelta
from unittest.mock import Mock
from uuid import UUID

import pytest
from sqlalchemy import create_engine, select, update
from sqlalchemy.ext.asyncio import async_sessionmaker
from sqlalchemy.orm import Session

from app.integrations import mailer
from app.modules.events.models import Round
from app.modules.submissions.jobs import SubmissionJobs
from app.modules.submissions.models import DeadlineReminder, FileUpload, Submission, SubmissionFile
from app.modules.submissions.repository import SubmissionJobRepository
from app.modules.teams.models import Team
from tests.test_auth import database_query
from tests.test_submissions import presign, submit


@pytest.fixture
def job_engine(submission_world):
    w = submission_world
    driver = "sqlite" if w.engine.dialect.name == "sqlite" else "postgresql+psycopg"
    engine = create_engine(w.engine.url.set(drivername=driver))
    try:
        yield engine
    finally:
        engine.dispose()


def test_reminders_dedupe_two_milestones_and_no_ambiguous_retry(
    submission_world, job_engine, auth_settings, monkeypatch
):
    w = submission_world
    deliver = Mock()
    monkeypatch.setattr(mailer, "send_email", deliver)
    with Session(job_engine, expire_on_commit=False) as session:
        jobs = SubmissionJobs(SubmissionJobRepository(session), auth_settings)
        assert jobs.remind() == 1
        assert jobs.remind() == 0
        assert deliver.call_count == 1
    database_query(
        w.engine,
        update(Round)
        .where(Round.id == UUID(w.round["id"]))
        .values(submission_deadline=w.now + timedelta(minutes=30)),
    )
    deliver.side_effect = RuntimeError("ambiguous SMTP receipt")
    with Session(job_engine, expire_on_commit=False) as session:
        jobs = SubmissionJobs(SubmissionJobRepository(session), auth_settings)
        assert jobs.remind() == 0
        assert jobs.remind() == 0
        assert deliver.call_count == 2
        assert sorted(session.scalars(select(DeadlineReminder.status))) == ["accepted", "failed"]


def test_reminders_skip_ineligible_and_unapproved(
    submission_world, job_engine, auth_settings, monkeypatch
):
    w = submission_world
    deliver = Mock()
    monkeypatch.setattr(mailer, "send_email", deliver)
    database_query(
        w.engine, update(Team).where(Team.id == UUID(w.team["id"])).values(status="pending")
    )
    with Session(job_engine, expire_on_commit=False) as session:
        assert SubmissionJobs(SubmissionJobRepository(session), auth_settings).remind() == 0
    deliver.assert_not_called()


def test_cleanup_temporary_only_preserves_receipts(submission_world, job_engine, auth_settings):
    w = submission_world
    key = presign(w).json()["file_key"]
    w.objects[key] = b"%PDF-content"
    assert submit(w, body={**w.body, "file_keys": [key]}).status_code == 201
    unused = presign(w).json()["file_key"]
    w.objects[unused] = b"unsubmitted"
    recent = presign(w).json()["file_key"]
    w.objects[recent] = b"recent"
    database_query(
        w.engine,
        update(FileUpload)
        .where(FileUpload.key.in_([key, unused]))
        .values(created_at=w.now - timedelta(hours=25)),
    )
    with Session(job_engine, expire_on_commit=False) as session:
        jobs = SubmissionJobs(SubmissionJobRepository(session), auth_settings)
        assert jobs.cleanup() == 2
        assert jobs.cleanup() == 0
        assert session.scalar(select(Submission.id))
        assert session.scalar(select(SubmissionFile.id))
    assert recent in w.objects and key not in w.objects and unused not in w.objects
    assert list(w.sealed.values()) == [b"%PDF-content"]


def test_cleanup_skips_file_being_sealed_on_postgres(submission_world, job_engine, auth_settings):
    w = submission_world
    if w.engine.dialect.name != "postgresql":
        pytest.skip("SKIP LOCKED requires PostgreSQL")
    key = presign(w).json()["file_key"]
    w.objects[key] = b"%PDF-content"
    database_query(
        w.engine,
        update(FileUpload)
        .where(FileUpload.key == key)
        .values(created_at=w.now - timedelta(hours=25)),
    )

    def cleanup():
        with Session(job_engine, expire_on_commit=False) as session:
            return SubmissionJobs(SubmissionJobRepository(session), auth_settings).cleanup()

    async def check():
        async with async_sessionmaker(w.engine)() as session:
            await session.scalar(select(FileUpload).where(FileUpload.key == key).with_for_update())
            assert await asyncio.to_thread(cleanup) == 0
            assert key in w.objects
            await session.rollback()
        assert await asyncio.to_thread(cleanup) == 1

    asyncio.run(check())
