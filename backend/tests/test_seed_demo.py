import asyncio
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.core.schemas import utc
from app.core.security import password_hasher
from app.modules.auth.models import AuditLog, EventRole, User
from app.modules.events.models import Event, Prize, Round, Track
from app.modules.teams.models import Team, TeamMember
from app.seed_demo import (
    EVENT_CONTENT,
    REFERENCE_REPOS,
    clean_demo,
    demo_id,
    require_local_database,
    seed_demo,
)


def test_demo_dataset_is_consistent_and_reruns_preserve_changes(auth_engine):
    async def check():
        factory = async_sessionmaker(auth_engine, expire_on_commit=False)
        now = datetime.now(UTC)
        async with factory.begin() as session:
            session.add(
                User(
                    email="existing@example.com",
                    full_name="Existing administrator",
                    password_hash="preserve-existing-hash",
                    is_admin=True,
                    email_verified=True,
                )
            )
        async with factory.begin() as session:
            assert await seed_demo(session, "TestDemo2026!", now)
        async with factory.begin() as session:
            expected = {
                User: 20,
                Event: 4,
                Track: 8,
                Round: 8,
                Prize: 12,
                Team: 12,
                TeamMember: 36,
                EventRole: 62,
                AuditLog: 1,
            }
            for model, count in expected.items():
                assert await session.scalar(select(func.count()).select_from(model)) == count
            organizer = await session.get(User, demo_id("organizer"))
            assert password_hasher.verify("TestDemo2026!", organizer.password_hash)
            assert not organizer.is_admin and organizer.email_verified and organizer.is_active
            existing = await session.scalar(select(User).where(User.is_admin.is_(True)))
            assert existing.password_hash == "preserve-existing-hash"
            for team in (await session.scalars(select(Team))).all():
                members = (
                    await session.scalars(
                        select(TeamMember).where(
                            TeamMember.team_id == team.id,
                        )
                    )
                ).all()
                assert any(m.user_id == team.leader_id and m.status == "active" for m in members)
                track = await session.get(Track, team.track_id)
                assert track.event_id == team.event_id
                assert all(m.event_id == team.event_id for m in members)
                team_event = await session.get(Event, team.event_id)
                assert utc(team_event.created_at) <= utc(team.created_at)
                for member in members:
                    user = await session.get(User, member.user_id)
                    assert utc(user.created_at) <= utc(member.joined_at)
                    assert utc(team.created_at) <= utc(member.joined_at)
                if team.status == "approved":
                    assert team.repo_url in REFERENCE_REPOS
                    assert all(m.status == "active" for m in members)
                    assert team.reviewed_at is not None
                else:
                    assert team.repo_url is None
            for role in (await session.scalars(select(EventRole))).all():
                user = await session.get(User, role.user_id)
                role_event = await session.get(Event, role.event_id)
                assert utc(user.created_at) <= utc(role.created_at)
                assert utc(role_event.created_at) <= utc(role.created_at)
                if role.role == "participant":
                    assert utc(role_event.registration_opens_at) <= utc(role.created_at)
                    assert utc(role.created_at) < utc(role_event.registration_closes_at)
            event = await session.get(Event, demo_id("open"))
            event.name = "Edited by organizer"
            original_deadline = event.registration_closes_at
            original_hash = organizer.password_hash
        async with factory.begin() as session:
            assert not await seed_demo(session, "AnotherPassword!", now + timedelta(days=2))
            event = await session.get(Event, demo_id("open"))
            assert event.name == "Edited by organizer"
            assert event.registration_closes_at == original_deadline
            assert (await session.get(User, demo_id("organizer"))).password_hash == original_hash
            assert await session.scalar(select(func.count()).select_from(Team)) == 12

    asyncio.run(check())


def test_clean_legacy_demo_is_scoped_and_idempotent(auth_engine):
    async def check():
        factory = async_sessionmaker(auth_engine, expire_on_commit=False)
        now = datetime.now(UTC)
        async with factory.begin() as session:
            await seed_demo(session, "TestDemo2026!", now)
            seed = await session.get(AuditLog, demo_id("seed"))
            seed.data = {key: value for key, value in seed.data.items() if key != "version"}
            event = await session.get(Event, demo_id("open"))
            event.name = "SEAL Innovation — Mở đăng ký"
            event.description = (
                "Dữ liệu demo local SEAL. Xây dựng sản phẩm công nghệ giải quyết "
                "vấn đề thực tế trong giáo dục, cộng đồng và phát triển bền vững."
            )
            event.created_at = now
            team = await session.get(Team, demo_id("open/team/0"))
            team.repo_url = None
            user = await session.get(User, demo_id("student01"))
            user.created_at = now
            original_hash = user.password_hash
            original_schedule = event.starts_at
            edited = await session.get(Event, demo_id("draft"))
            edited.name = "Organizer's custom title"
            edited.description = "Organizer's custom description"
            edited_team = await session.get(Team, demo_id("open/team/1"))
            edited_team.repo_url = "https://github.com/custom/owned-repo"
            session.add(
                User(
                    email="real@example.com",
                    full_name="Real account",
                    password_hash="unchanged",
                    created_at=now,
                )
            )
        async with factory.begin() as session:
            assert await clean_demo(session)
        async with factory.begin() as session:
            event = await session.get(Event, demo_id("open"))
            assert (event.name, event.description) == EVENT_CONTENT["open"]
            assert utc(event.created_at) < utc(event.registration_opens_at)
            assert utc(event.starts_at) == utc(original_schedule)
            team = await session.get(Team, demo_id("open/team/0"))
            assert team.repo_url == REFERENCE_REPOS[0]
            user = await session.get(User, demo_id("student01"))
            assert user.password_hash == original_hash
            assert utc(user.created_at) < utc(team.created_at)
            edited = await session.get(Event, demo_id("draft"))
            assert edited.name == "Organizer's custom title"
            assert edited.description == "Organizer's custom description"
            edited_team = await session.get(Team, demo_id("open/team/1"))
            assert edited_team.repo_url == "https://github.com/custom/owned-repo"
            real = await session.scalar(select(User).where(User.email == "real@example.com"))
            assert real.password_hash == "unchanged" and utc(real.created_at) == now
            assert not await clean_demo(session)
            assert await session.scalar(select(func.count()).select_from(Team)) == 12
            assert await session.scalar(select(func.count()).select_from(AuditLog)) == 2

    asyncio.run(check())


def test_seed_conflict_rolls_back_without_changing_existing_account(auth_engine):
    async def check():
        factory = async_sessionmaker(auth_engine, expire_on_commit=False)
        async with factory.begin() as session:
            session.add(
                User(
                    email="demo.judge1@example.com",
                    full_name="Existing",
                    password_hash="original",
                    email_verified=False,
                )
            )
        with pytest.raises(ValueError, match="already exists"):
            async with factory.begin() as session:
                await seed_demo(session, "TestDemo2026!", datetime.now(UTC))
        async with factory() as session:
            assert await session.scalar(select(func.count()).select_from(User)) == 1
            assert await session.scalar(select(func.count()).select_from(Event)) == 0
            user = await session.scalar(select(User))
            assert user.password_hash == "original" and not user.email_verified

    asyncio.run(check())


@pytest.mark.parametrize(
    "url",
    [
        "postgresql+asyncpg://user:pass@db.example.com:5434/seal",
        "postgresql+asyncpg://user:pass@127.0.0.1:5432/seal",
        "postgresql+asyncpg://user:pass@127.0.0.1:5434/production",
        "sqlite+aiosqlite:///demo.db",
    ],
)
def test_demo_rejects_nonlocal_database(url):
    with pytest.raises(ValueError, match="only supports"):
        require_local_database(url)


def test_demo_accepts_project_local_database():
    require_local_database("postgresql+asyncpg://seal:password@127.0.0.1:5434/seal")
