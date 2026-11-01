from datetime import datetime
from uuid import UUID

from sqlalchemy import delete, func, inspect, or_, select, text, update
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import ApiError
from app.modules.auth.models import (
    AuditLog,
    EmailVerificationToken,
    EventRole,
    PasswordResetToken,
    RefreshSession,
    User,
)
from app.modules.auth.schemas import AuditLogOutput, DataCounts


class AuthRepository:
    async def event_started_at(self, event_id: UUID) -> datetime | None:
        return await self.session.scalar(
            select(func.min(AuditLog.created_at)).where(
                AuditLog.action == "event.transitioned",
                AuditLog.target_type == "event",
                AuditLog.target_id == str(event_id),
                AuditLog.data["after"].as_string() == "ongoing",
            )
        )

    @staticmethod
    def sync_recipients(session: object, event_id: UUID) -> list[str]:
        return list(
            session.scalars(
                select(User.email)
                .join(EventRole, EventRole.user_id == User.id)
                .where(
                    EventRole.event_id == event_id,
                    EventRole.role == "organizer",
                    User.is_active.is_(True),
                    User.email_verified.is_(True),
                    User.is_admin.is_(False),
                )
            )
        )

    @staticmethod
    def reminder_users(session: object, ids: list[UUID]) -> dict[UUID, object]:
        return {
            u.id: u
            for u in session.scalars(
                select(User).where(
                    User.id.in_(ids),
                    User.is_active.is_(True),
                    User.email_verified.is_(True),
                    User.is_admin.is_(False),
                )
            )
        }

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_user(self, user_id: UUID, *, lock: bool = False) -> User | None:
        query = select(User).where(User.id == user_id).execution_options(populate_existing=True)
        return await self.session.scalar(query.with_for_update() if lock else query)

    async def find_email(self, email: str, *, lock: bool = False) -> User | None:
        query = select(User).where(User.email == email)
        if lock:
            query = query.with_for_update()
        return await self.session.scalar(query)

    async def create_user(self, email: str, password_hash: str, full_name: str) -> User:
        user = User(email=email, password_hash=password_hash, full_name=full_name)
        self.session.add(user)
        try:
            await self.session.flush()
        except IntegrityError as exc:
            await self.session.rollback()
            raise ApiError(409, "EMAIL_TAKEN", "Email is already registered") from exc
        return user

    async def update_profile(self, user: User, values: dict[str, object]) -> User:
        for key, value in values.items():
            setattr(user, key, value)
        await self.session.flush()
        return user

    async def add_verification(
        self, user_id: UUID, hashed_token: str, now: datetime, expires: datetime
    ) -> None:
        await self.session.execute(
            delete(EmailVerificationToken).where(EmailVerificationToken.user_id == user_id)
        )
        self.session.add(
            EmailVerificationToken(
                user_id=user_id, token_hash=hashed_token, created_at=now, expires_at=expires
            )
        )

    async def last_verification(self, user_id: UUID) -> EmailVerificationToken | None:
        return await self.session.scalar(
            select(EmailVerificationToken).where(EmailVerificationToken.user_id == user_id)
        )

    async def consume_verification(self, hashed_token: str, now: datetime) -> User | None:
        user_id = await self.session.scalar(
            select(EmailVerificationToken.user_id).where(
                EmailVerificationToken.token_hash == hashed_token,
                EmailVerificationToken.expires_at > now,
            )
        )
        if user_id is None:
            return None
        # Cùng thứ tự khóa user → token như resend để tránh deadlock khi gọi đồng thời.
        user = await self.session.scalar(select(User).where(User.id == user_id).with_for_update())
        user_id = await self.session.scalar(
            delete(EmailVerificationToken)
            .where(
                EmailVerificationToken.token_hash == hashed_token,
                EmailVerificationToken.expires_at > now,
            )
            .returning(EmailVerificationToken.user_id)
        )
        if user_id is None:
            return None
        user.email_verified = True
        await self.session.flush()
        return user

    async def create_session(
        self, session_id: UUID, user_id: UUID, hashed_token: str, expires: datetime
    ) -> None:
        self.session.add(
            RefreshSession(
                id=session_id, user_id=user_id, token_hash=hashed_token, expires_at=expires
            )
        )

    async def session_user(
        self, session_id: UUID, user_id: UUID, now: datetime, *, lock: bool = False
    ) -> User | None:
        query = (
            select(User)
            .join(RefreshSession, RefreshSession.user_id == User.id)
            .where(
                User.id == user_id,
                RefreshSession.id == session_id,
                RefreshSession.expires_at > now,
            )
        )
        try:
            return await self.session.scalar(query.with_for_update(of=User) if lock else query)
        except (SQLAlchemyError, OSError, TimeoutError):
            raise ApiError(
                503, "AUTH_UNAVAILABLE", "Authentication is temporarily unavailable"
            ) from None

    async def rotate_session(
        self, session_id: UUID, old_hash: str, new_hash: str, expires: datetime, now: datetime
    ) -> bool:
        result = await self.session.execute(
            update(RefreshSession)
            .where(
                RefreshSession.id == session_id,
                RefreshSession.token_hash == old_hash,
                RefreshSession.expires_at > now,
            )
            .values(token_hash=new_hash, expires_at=expires)
        )
        return result.rowcount == 1

    async def revoke_session(self, hashed_token: str) -> None:
        await self.session.execute(
            delete(RefreshSession).where(RefreshSession.token_hash == hashed_token)
        )

    async def commit(self) -> None:
        await self.session.commit()

    async def last_reset(self, user_id: UUID) -> PasswordResetToken | None:
        return await self.session.scalar(
            select(PasswordResetToken).where(PasswordResetToken.user_id == user_id)
        )

    async def add_reset(
        self, user_id: UUID, hashed_token: str, now: datetime, expires: datetime
    ) -> None:
        await self.session.execute(
            delete(PasswordResetToken).where(PasswordResetToken.user_id == user_id)
        )
        self.session.add(
            PasswordResetToken(
                user_id=user_id, token_hash=hashed_token, created_at=now, expires_at=expires
            )
        )

    async def consume_reset(self, hashed_token: str, now: datetime, password_hash: str) -> bool:
        user_id = await self.session.scalar(
            select(PasswordResetToken.user_id).where(
                PasswordResetToken.token_hash == hashed_token, PasswordResetToken.expires_at > now
            )
        )
        if user_id is None:
            return False
        user = await self.get_user(user_id, lock=True)
        if user is None or not user.is_active or not user.email_verified:
            return False
        consumed = await self.session.scalar(
            delete(PasswordResetToken)
            .where(
                PasswordResetToken.token_hash == hashed_token, PasswordResetToken.expires_at > now
            )
            .returning(PasswordResetToken.user_id)
        )
        if consumed is None:
            return False
        user.password_hash = password_hash
        await self.revoke_user_sessions(user_id)
        return True

    async def revoke_user_sessions(self, user_id: UUID) -> None:
        await self.session.execute(delete(RefreshSession).where(RefreshSession.user_id == user_id))

    async def event_roles(self, user_id: UUID) -> list[EventRole]:
        return list(
            await self.session.scalars(
                select(EventRole)
                .where(EventRole.user_id == user_id)
                .order_by(EventRole.event_id, EventRole.role)
            )
        )

    async def lock_users(self, user_ids: list[UUID]) -> list[User]:
        return list(
            await self.session.scalars(
                select(User)
                .where(User.id.in_(user_ids))
                .order_by(User.id)
                .with_for_update()
                .execution_options(populate_existing=True)
            )
        )

    async def users(self, user_ids: list[UUID]) -> list[User]:
        return list(await self.session.scalars(select(User).where(User.id.in_(user_ids))))

    async def roles_in_event(self, event_id: UUID) -> list[EventRole]:
        return list(
            await self.session.scalars(select(EventRole).where(EventRole.event_id == event_id))
        )

    async def role_page(
        self, event_id: UUID, role: str | None, q: str | None, limit: int, offset: int
    ) -> tuple[list[EventRole], int]:
        query = (
            select(EventRole)
            .join(User, User.id == EventRole.user_id)
            .where(EventRole.event_id == event_id)
        )
        if role:
            query = query.where(EventRole.role == role)
        if q:
            query = query.where(
                or_(
                    func.lower(User.email).contains(q.lower(), autoescape=True),
                    func.lower(User.full_name).contains(q.lower(), autoescape=True),
                )
            )
        total = await self.session.scalar(select(func.count()).select_from(query.subquery()))
        return list(
            await self.session.scalars(
                query.order_by(EventRole.created_at, EventRole.id).limit(limit).offset(offset)
            )
        ), total

    async def participant_counts(self, event_ids: list[UUID]) -> dict[UUID, int]:
        rows = await self.session.execute(
            select(EventRole.event_id, func.count())
            .where(EventRole.event_id.in_(event_ids), EventRole.role == "participant")
            .group_by(EventRole.event_id)
        )
        return dict(rows.all())

    async def add_role(self, user_id: UUID, event_id: UUID, role: str) -> EventRole:
        entry = EventRole(user_id=user_id, event_id=event_id, role=role)
        self.session.add(entry)
        try:
            await self.session.flush()
        except IntegrityError:
            await self.session.rollback()
            raise ApiError(
                409, "ROLE_CONFLICT", "Role already exists or event is invalid"
            ) from None
        return entry

    async def delete_role(self, role_id: UUID) -> None:
        await self.session.execute(delete(EventRole).where(EventRole.id == role_id))

    async def has_event_role(self, user_id: UUID, event_id: UUID, roles: tuple[str, ...]) -> bool:
        return (
            await self.session.scalar(
                select(EventRole.id)
                .where(
                    EventRole.user_id == user_id,
                    EventRole.event_id == event_id,
                    EventRole.role.in_(roles),
                )
                .limit(1)
            )
            is not None
        )

    async def list_users(self, q: str | None, limit: int, offset: int) -> tuple[list[User], int]:
        query = select(User)
        if q:
            query = query.where(
                or_(
                    func.lower(User.email).contains(q.lower(), autoescape=True),
                    func.lower(User.full_name).contains(q.lower(), autoescape=True),
                )
            )
        total = await self.session.scalar(select(func.count()).select_from(query.subquery()))
        items = await self.session.scalars(
            query.order_by(User.created_at.desc(), User.id).limit(limit).offset(offset)
        )
        return list(items), total

    async def write_audit_log(
        self, actor_id: UUID, action: str, target_type: str, target_id: str, data: dict[str, object]
    ) -> None:
        self.session.add(
            AuditLog(
                actor_id=actor_id,
                action=action,
                target_type=target_type,
                target_id=target_id,
                data=data,
            )
        )
        await self.session.flush()

    async def list_audit_logs(
        self, actor_id: UUID | None, action: str | None, limit: int, offset: int
    ) -> tuple[list[AuditLogOutput], int]:
        query = select(AuditLog, User.email).join(User, User.id == AuditLog.actor_id)
        if actor_id is not None:
            query = query.where(AuditLog.actor_id == actor_id)
        if action is not None:
            query = query.where(AuditLog.action == action)
        total = await self.session.scalar(select(func.count()).select_from(query.subquery()))
        rows = await self.session.execute(
            query.order_by(AuditLog.created_at.desc(), AuditLog.id).limit(limit).offset(offset)
        )
        return [
            AuditLogOutput(
                id=log.id,
                actor_id=log.actor_id,
                actor_email=email,
                action=log.action,
                target_type=log.target_type,
                target_id=log.target_id,
                data=log.data,
                created_at=log.created_at,
            )
            for log, email in rows
        ], total

    async def has_admin(self) -> bool:
        return (
            await self.session.scalar(select(User.id).where(User.is_admin.is_(True)).limit(1))
            is not None
        )

    async def lock_admin_bootstrap(self) -> None:
        if self.session.bind.dialect.name == "postgresql":
            from sqlalchemy import text

            await self.session.execute(text("SELECT pg_advisory_xact_lock(73421001)"))

    async def system_data(self) -> DataCounts:
        connection = await self.session.connection()
        tables = await connection.run_sync(lambda sync: set(inspect(sync).get_table_names()))
        counts = DataCounts()
        for field, table in {
            "users": "users",
            "events": "events",
            "teams": "teams",
            "submissions": "submissions",
            "commits": "commits",
            "ai_reviews": "commit_reviews",
            "audit_logs": "audit_logs",
        }.items():
            if table in tables:
                # Tên bảng từ whitelist cố định, không nhận identifier từ client.
                setattr(
                    counts,
                    field,
                    await self.session.scalar(text(f'SELECT COUNT(*) FROM "{table}"')),
                )
        counts.active_users = await self.session.scalar(
            select(func.count()).select_from(User).where(User.is_active.is_(True))
        )
        counts.admins = await self.session.scalar(
            select(func.count()).select_from(User).where(User.is_admin.is_(True))
        )
        if connection.dialect.name == "postgresql":
            try:
                async with self.session.begin_nested():
                    counts.database_bytes = await self.session.scalar(
                        select(func.pg_database_size(func.current_database()))
                    )
            except SQLAlchemyError:
                # Quyền đo dung lượng không phải điều kiện để đọc thống kê tài khoản.
                counts.database_bytes = None
        return counts
