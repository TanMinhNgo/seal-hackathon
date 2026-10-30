"""Local demo fixtures for the implemented Phase 1–2 schema; no external side effects."""

import argparse
import asyncio
import logging
import os
from datetime import UTC, datetime, timedelta
from getpass import getpass
from secrets import token_urlsafe
from uuid import NAMESPACE_URL, UUID, uuid5

from sqlalchemy import func, select
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.db import engine, session_factory
from app.core.schemas import utc
from app.core.security import password_hasher
from app.modules.auth.models import AuditLog, EventRole, User
from app.modules.events.models import Event, Prize, Round, Track
from app.modules.teams.models import Team, TeamMember

logger = logging.getLogger(__name__)

EVENT_CONTENT = {
    "draft": (
        "SEAL Future Lab 2027",
        "Ươm tạo ý tưởng ứng dụng AI trong học tập và đời sống. Các đội khảo sát nhu cầu, "
        "xây dựng nguyên mẫu và đề xuất kế hoạch thử nghiệm với người dùng.",
    ),
    "open": (
        "SEAL Innovation Challenge 2026",
        "Cuộc thi phát triển sản phẩm số phục vụ giáo dục và cộng đồng. "
        "Các đội lựa chọn bài toán, xây dựng giải pháp và trình bày nguyên mẫu hoạt động.",
    ),
    "ongoing": (
        "SEAL Build for Education 2026",
        "Phát triển công cụ hỗ trợ tự học và chia sẻ tri thức trong cộng đồng. "
        "Sản phẩm cần có luồng sử dụng rõ ràng và được thử nghiệm với nhóm người học.",
    ),
    "judging": (
        "SEAL Community Impact 2026",
        "Xây dựng giải pháp giúp cộng đồng tiếp cận kiến thức và dịch vụ số. "
        "Ban giám khảo đánh giá tính hữu ích, chất lượng kỹ thuật và khả năng áp dụng.",
    ),
}

# Repo tham chiếu công khai cho fixture, không phải sản phẩm do các đội sở hữu.
REFERENCE_REPOS = (
    "https://github.com/microsoft/generative-ai-for-beginners",
    "https://github.com/fastapi/full-stack-fastapi-template",
    "https://github.com/vercel/next-learn",
    "https://github.com/streamlit/hello",
)


def demo_id(key: str) -> UUID:
    return uuid5(NAMESPACE_URL, f"seal/local-demo/v1/{key}")


def require_local_database(url: str) -> None:
    target = make_url(url)
    if (
        target.drivername != "postgresql+asyncpg"
        or target.host not in {"127.0.0.1", "localhost"}
        or target.port != 5434
        or target.database != "seal"
    ):
        raise ValueError("Demo seed only supports the local seal database on port 5434")


async def seed_demo(session: AsyncSession, password: str, now: datetime) -> bool:
    """Insert one atomic dataset. Caller owns the transaction; reruns preserve edits."""
    if not 8 <= len(password) <= 128:
        raise ValueError("Demo password must contain 8–128 characters")
    if now.tzinfo is None or now.utcoffset() is None:
        raise ValueError("Seed time must include a timezone")
    now = now.astimezone(UTC)
    if await session.get(AuditLog, demo_id("seed")):
        return False

    accounts = [
        ("organizer", "Nguyễn Minh Anh"),
        ("judge1", "Trần Hoàng Nam"),
        ("judge2", "Lê Thu Hà"),
        ("mentor1", "Phạm Đức Huy"),
        ("mentor2", "Võ Ngọc Linh"),
    ] + [
        (f"student{index:02}", name)
        for index, name in enumerate(
            [
                "Nguyễn Gia Bảo",
                "Trần Minh Châu",
                "Lê Hải Đăng",
                "Phạm Khánh An",
                "Hoàng Anh Khoa",
                "Vũ Thanh Mai",
                "Đặng Quốc Huy",
                "Bùi Ngọc Anh",
                "Đỗ Minh Quân",
                "Hồ Thảo Vy",
                "Ngô Tuấn Kiệt",
                "Dương Bảo Ngọc",
                "Lý Phương Linh",
                "Mai Đức Thành",
            ],
            start=1,
        )
    ]
    emails = [f"demo.{key}@example.com" for key, _ in accounts]
    if await session.scalar(select(User.id).where(User.email.in_(emails)).limit(1)):
        raise ValueError("Demo email already exists; no existing account will be changed")
    hashed = password_hasher.hash(password)
    for key, name in accounts:
        session.add(
            User(
                id=demo_id(key),
                email=f"demo.{key}@example.com",
                full_name=name,
                password_hash=hashed,
                email_verified=True,
                is_active=True,
                is_admin=False,
                created_at=now - timedelta(days=60),
            )
        )
    await session.flush()

    scenarios = [
        ("draft", 40),
        ("open", 10),
        ("ongoing", -2),
        ("judging", -12),
    ]
    for status, start_days in scenarios:
        event_id = demo_id(status)
        starts = now + timedelta(days=start_days)
        ends = starts + timedelta(days=7)
        closes = starts - timedelta(days=1)
        session.add(
            Event(
                id=event_id,
                name=EVENT_CONTENT[status][0],
                slug=f"demo-seal-{status}",
                status=status,
                description=EVENT_CONTENT[status][1],
                rules="Đội 2–4 thành viên. Tôn trọng bản quyền, công khai nguồn tham khảo.",
                registration_opens_at=starts - timedelta(days=20),
                registration_closes_at=closes,
                starts_at=starts,
                ends_at=ends,
                min_team_size=2,
                max_team_size=4,
                created_at=now - timedelta(days=45),
            )
        )
        await session.flush()
        for key, role in [
            ("organizer", "organizer"),
            ("judge1", "judge"),
            ("judge2", "judge"),
            ("mentor1", "mentor"),
            ("mentor2", "mentor"),
        ]:
            session.add(
                EventRole(
                    user_id=demo_id(key),
                    event_id=event_id,
                    role=role,
                    created_at=now - timedelta(days=44),
                )
            )
        for order, title in enumerate(["Ý tưởng & nguyên mẫu", "Hoàn thiện & demo"], start=1):
            round_start = starts if order == 1 else starts + timedelta(days=3)
            round_end = starts + timedelta(days=3) if order == 1 else ends
            session.add(
                Round(
                    event_id=event_id,
                    name=title,
                    order=order,
                    starts_at=round_start,
                    submission_deadline=round_end - timedelta(hours=2),
                    ends_at=round_end,
                    required_judges=2,
                )
            )
        for index, (title, description) in enumerate(
            [
                ("AI & Giáo dục", "Công cụ học tập, trợ lý AI và hỗ trợ giáo viên."),
                ("Công nghệ cộng đồng", "Giải pháp số cho cộng đồng và môi trường."),
            ]
        ):
            session.add(
                Track(
                    id=demo_id(f"{status}/track/{index}"),
                    event_id=event_id,
                    name=title,
                    description=description,
                )
            )
        for rank, (title, value) in enumerate(
            [
                ("Giải Nhất", 15000000),
                ("Giải Nhì", 10000000),
                ("Giải Ba", 5000000),
            ],
            start=1,
        ):
            session.add(
                Prize(
                    event_id=event_id,
                    rank=rank,
                    name=title,
                    value=value,
                    description="Giá trị minh họa (VND), không phải giải thưởng thực tế.",
                )
            )
        await session.flush()
        if status == "draft":
            continue
        for index in range(1, 15):
            session.add(
                EventRole(
                    user_id=demo_id(f"student{index:02}"),
                    event_id=event_id,
                    role="participant",
                    created_at=starts - timedelta(days=15),
                )
            )
        for index, title in enumerate(["Lotus AI", "Green Byte", "EduSpark", "Mekong Makers"]):
            team_id = demo_id(f"{status}/team/{index}")
            team_status = (
                ["approved", "approved", "pending", "rejected"][index]
                if status == "open"
                else "approved"
            )
            reviewed = team_status != "pending"
            session.add(
                Team(
                    id=team_id,
                    event_id=event_id,
                    name=title,
                    status=team_status,
                    track_id=demo_id(f"{status}/track/{index % 2}"),
                    leader_id=demo_id(f"student{index * 3 + 1:02}"),
                    invite_code=token_urlsafe(24),
                    invite_expires_at=closes,
                    review_note=(
                        "Chưa khai báo kho mã nguồn công khai để ban tổ chức kiểm tra."
                        if team_status == "rejected"
                        else None
                    ),
                    reviewed_at=starts - timedelta(days=12) if reviewed else None,
                    created_at=starts - timedelta(days=14),
                    repo_url=REFERENCE_REPOS[index] if team_status == "approved" else None,
                )
            )
            await session.flush()
            for member in range(3):
                session.add(
                    TeamMember(
                        team_id=team_id,
                        event_id=event_id,
                        user_id=demo_id(f"student{index * 3 + member + 1:02}"),
                        status="pending" if team_status == "pending" and member == 2 else "active",
                        joined_at=starts - timedelta(days=14),
                    )
                )
        await session.flush()

    session.add(
        AuditLog(
            id=demo_id("seed"),
            actor_id=demo_id("organizer"),
            action="demo.seeded",
            target_type="dataset",
            target_id="seal/local-demo/v1",
            data={"source": "local_demo_seed", "version": 2, "users": 19, "events": 4, "teams": 12},
            created_at=now,
        )
    )
    await session.flush()
    return True


async def clean_demo(session: AsyncSession) -> bool:
    """Upgrade only known v1 fixture fields, preserving user edits and login credentials."""
    seed = await session.get(AuditLog, demo_id("seed"))
    if seed is None:
        raise ValueError("No demo dataset found; run the seed first")
    if seed.data.get("version") == 2 or await session.get(AuditLog, demo_id("clean-v2")):
        return False
    seeded_at = utc(seed.created_at)
    keys = ["organizer", "judge1", "judge2", "mentor1", "mentor2"] + [
        f"student{index:02}" for index in range(1, 15)
    ]
    for key in keys:
        user = await session.get(User, demo_id(key))
        if user is not None and user.email == f"demo.{key}@example.com":
            user.created_at = min(utc(user.created_at), seeded_at - timedelta(days=60))
    old_names = {
        "draft": "SEAL Next — Bản nháp",
        "open": "SEAL Innovation — Mở đăng ký",
        "ongoing": "SEAL Build — Đang thi",
        "judging": "SEAL Impact — Đang chấm",
    }
    old_description = (
        "Dữ liệu demo local SEAL. Xây dựng sản phẩm công nghệ giải quyết "
        "vấn đề thực tế trong giáo dục, cộng đồng và phát triển bền vững."
    )
    for status, old_name in old_names.items():
        event = await session.get(Event, demo_id(status))
        if event is None:
            continue
        if event.name == old_name:
            event.name = EVENT_CONTENT[status][0]
        if event.description == old_description:
            event.description = EVENT_CONTENT[status][1]
        event.created_at = min(utc(event.created_at), seeded_at - timedelta(days=45))
        staff_roles = (
            await session.scalars(
                select(EventRole).where(
                    EventRole.event_id == event.id,
                    EventRole.user_id.in_([demo_id(key) for key in keys[:5]]),
                )
            )
        ).all()
        for role in staff_roles:
            role.created_at = min(utc(role.created_at), seeded_at - timedelta(days=44))
        for index in range(4):
            team = await session.get(Team, demo_id(f"{status}/team/{index}"))
            if team is None:
                continue
            if team.status == "approved" and team.repo_url is None:
                team.repo_url = REFERENCE_REPOS[index]
            if team.review_note == "Cần bổ sung mô tả ý tưởng trước khi duyệt lại.":
                team.review_note = "Chưa khai báo kho mã nguồn công khai để ban tổ chức kiểm tra."
    session.add(
        AuditLog(
            id=demo_id("clean-v2"),
            actor_id=seed.actor_id,
            action="demo.cleaned",
            target_type="dataset",
            target_id=seed.target_id,
            data={
                "source": "local_demo_seed",
                "version": 2,
                "changes": ["event_content", "creation_times", "reference_repos", "review_note"],
            },
        )
    )
    await session.flush()
    return True


async def run(password: str, *, clean: bool = False) -> bool:
    require_local_database(str(get_settings().database_url))
    try:
        async with session_factory.begin() as session:
            # Serialize seed runs without touching existing application records.
            await session.execute(select(func.pg_advisory_xact_lock(73419026)))
            if clean:
                return await clean_demo(session)
            return await seed_demo(session, password, datetime.now(UTC))
    finally:
        await engine.dispose()


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Add local SEAL demo data without deleting records"
    )
    parser.add_argument("--clean", action="store_true", help="Clean the existing v1 demo fixtures")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    try:
        require_local_database(str(get_settings().database_url))
        password = (
            ""
            if args.clean
            else (os.environ.get("SEAL_DEMO_PASSWORD") or getpass("Demo account password: "))
        )
        created = asyncio.run(run(password, clean=args.clean))
    except ValueError as exc:
        parser.exit(1, f"{exc}\n")
    if args.clean:
        logger.info("Demo data cleaned." if created else "Demo data already clean; no changes.")
        return
    logger.info(
        "Created 19 demo users, 4 events, 12 teams."
        if created
        else "Demo dataset already seeded; existing data preserved."
    )


if __name__ == "__main__":
    main()
