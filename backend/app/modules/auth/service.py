import logging
from datetime import UTC, datetime, timedelta
from secrets import token_urlsafe
from uuid import UUID, uuid4

from fastapi.concurrency import run_in_threadpool

from app.core.config import Settings
from app.core.errors import ApiError
from app.core.security import (
    DUMMY_PASSWORD_HASH,
    VERIFY_TTL,
    decode_token,
    issue_tokens,
    password_hasher,
    token_hash,
)
from app.modules.auth.repository import AuthRepository
from app.modules.auth.schemas import (
    AdminUserInput,
    AuditLogPage,
    EventRoleOutput,
    LoginInput,
    ProfileInput,
    RegisterInput,
    ResetPasswordInput,
    Role,
    RoleRecord,
    UserOutput,
    UserPage,
)
from worker.tasks.send_email import send_email

logger = logging.getLogger(__name__)


class AuthService:
    async def event_started_at(self, event_id: UUID) -> datetime | None:
        return await self.repository.event_started_at(event_id)

    @staticmethod
    def sync_recipients(session: object, event_id: UUID) -> list[str]:
        return AuthRepository.sync_recipients(session, event_id)

    @staticmethod
    def reminder_users(session: object, ids: list[UUID]) -> dict[UUID, object]:
        return AuthRepository.reminder_users(session, ids)

    def __init__(self, repository: AuthRepository, settings: Settings) -> None:
        self.repository = repository
        self.settings = settings

    @staticmethod
    def require_active(user: UserOutput) -> None:
        if not user.is_active:
            raise ApiError(403, "ACCOUNT_DISABLED", "Account is disabled")

    async def queue_verification(self, email: str, raw_token: str) -> None:
        link = f"{str(self.settings.frontend_url).rstrip('/')}/verify-email?token={raw_token}"
        try:
            await run_in_threadpool(
                send_email.apply_async,
                args=[
                    email,
                    "SEAL - Verify your email",
                    f"Verify your email: {link}\nExpires in 24 hours.",
                ],
                argsrepr="(<redacted>,)",
                retry=False,
            )
        except Exception:
            raise ApiError(
                503,
                "EMAIL_QUEUE_UNAVAILABLE",
                "Account saved; request a new verification email later",
            ) from None

    async def register(self, data: RegisterInput) -> UserOutput:
        if await self.repository.find_email(str(data.email)):
            raise ApiError(409, "EMAIL_TAKEN", "Email is already registered")
        hashed_password = await run_in_threadpool(password_hasher.hash, data.password)
        user = await self.repository.create_user(str(data.email), hashed_password, data.full_name)
        now = datetime.now(UTC)
        raw_token = token_urlsafe(32)
        await self.repository.add_verification(
            user.id, token_hash(raw_token), now, now + VERIFY_TTL
        )
        output = UserOutput.model_validate(user)
        await self.repository.commit()
        # shortcut: queue lỗi sau commit cần resend, dùng outbox khi cần bảo đảm enqueue.
        await self.queue_verification(str(output.email), raw_token)
        return output

    async def resend_verification(self, email: str) -> None:
        user = await self.repository.find_email(email, lock=True)
        if user is None or user.email_verified or not user.is_active:
            return
        now = datetime.now(UTC)
        previous = await self.repository.last_verification(user.id)
        if previous:
            created = previous.created_at
            created = created.replace(tzinfo=UTC) if created.tzinfo is None else created
            if now - created < timedelta(seconds=60):
                return
        raw_token = token_urlsafe(32)
        await self.repository.add_verification(
            user.id, token_hash(raw_token), now, now + VERIFY_TTL
        )
        await self.repository.commit()
        await self.queue_verification(user.email, raw_token)

    async def verify_email(self, raw_token: str) -> None:
        user = await self.repository.consume_verification(token_hash(raw_token), datetime.now(UTC))
        if user is None:
            raise ApiError(400, "INVALID_TOKEN", "Invalid or expired verification token")
        self.require_active(UserOutput.model_validate(user))
        await self.repository.commit()

    async def login(self, data: LoginInput) -> tuple[str, str]:
        user = await self.repository.find_email(str(data.email), lock=True)
        valid = await run_in_threadpool(
            password_hasher.verify,
            data.password,
            user.password_hash if user else DUMMY_PASSWORD_HASH,
        )
        if user is None or not valid:
            raise ApiError(401, "INVALID_CREDENTIALS", "Email or password is incorrect")
        self.require_active(UserOutput.model_validate(user))
        if not user.email_verified:
            raise ApiError(403, "EMAIL_NOT_VERIFIED", "Verify your email before signing in")
        session_id = uuid4()
        access, refresh, expires = issue_tokens(self.settings, user.id, session_id)
        await self.repository.create_session(session_id, user.id, token_hash(refresh), expires)
        await self.repository.commit()
        return access, refresh

    async def current_user(self, access_token: str) -> UserOutput:
        user_id, session_id = decode_token(self.settings, access_token, "access")
        user = await self.repository.session_user(session_id, user_id, datetime.now(UTC))
        if user is None:
            raise ApiError(401, "INVALID_TOKEN", "Session is no longer valid")
        output = UserOutput.model_validate(user)
        self.require_active(output)
        if not output.email_verified:
            raise ApiError(403, "EMAIL_NOT_VERIFIED", "Email is not verified")
        return output

    async def refresh(self, raw_token: str) -> tuple[str, str]:
        user_id, session_id = decode_token(self.settings, raw_token, "refresh")
        now = datetime.now(UTC)
        user = await self.repository.session_user(session_id, user_id, now, lock=True)
        if user is None:
            raise ApiError(401, "INVALID_TOKEN", "Session is no longer valid")
        self.require_active(UserOutput.model_validate(user))
        if not user.email_verified:
            raise ApiError(403, "EMAIL_NOT_VERIFIED", "Email is not verified")
        access, refresh, expires = issue_tokens(self.settings, user_id, session_id)
        rotated = await self.repository.rotate_session(
            session_id, token_hash(raw_token), token_hash(refresh), expires, now
        )
        if not rotated:
            raise ApiError(401, "INVALID_TOKEN", "Refresh token has already been used or revoked")
        await self.repository.commit()
        return access, refresh

    async def logout(self, raw_token: str | None) -> None:
        if raw_token:
            await self.repository.revoke_session(token_hash(raw_token))
            await self.repository.commit()

    async def update_profile(self, current: UserOutput, data: ProfileInput) -> UserOutput:
        user = await self.repository.get_user(current.id)
        self.require_active(UserOutput.model_validate(user))
        user = await self.repository.update_profile(
            user, data.model_dump(mode="json", exclude_unset=True)
        )
        output = UserOutput.model_validate(user)
        await self.repository.commit()
        return output

    @staticmethod
    def require_admin(user: UserOutput) -> None:
        AuthService.require_active(user)
        if not user.is_admin:
            raise ApiError(403, "FORBIDDEN", "Administrator access is required")

    async def require_event_role(
        self, user: UserOutput, event_id: UUID, roles: tuple[Role, ...]
    ) -> None:
        self.require_active(user)
        if user.is_admin:
            raise ApiError(403, "FORBIDDEN", "Administrators cannot perform event operations")
        if not await self.repository.has_event_role(user.id, event_id, roles):
            raise ApiError(403, "FORBIDDEN", "Required event role is missing")

    async def event_roles(self, user: UserOutput) -> list[EventRoleOutput]:
        return [
            EventRoleOutput.model_validate(role)
            for role in await self.repository.event_roles(user.id)
        ]

    async def lock_actor(self, actor: UserOutput, others: tuple[UUID, ...] = ()) -> UserOutput:
        users = {
            user.id: user for user in await self.repository.lock_users(list({actor.id, *others}))
        }
        if actor.id not in users:
            raise ApiError(401, "INVALID_TOKEN", "User no longer exists")
        current = UserOutput.model_validate(users[actor.id])
        self.require_active(current)
        if not current.email_verified:
            raise ApiError(403, "EMAIL_NOT_VERIFIED", "Email is not verified")
        return current

    async def users(self, user_ids: list[UUID]) -> dict[UUID, UserOutput]:
        return {
            user.id: UserOutput.model_validate(user)
            for user in await self.repository.users(user_ids)
        }

    async def find_user(self, email: str) -> UserOutput:
        user = await self.repository.find_email(email)
        if user is None:
            raise ApiError(404, "USER_NOT_FOUND", "User does not exist")
        return UserOutput.model_validate(user)

    async def roles_in_event(self, event_id: UUID) -> list[RoleRecord]:
        return [
            RoleRecord.model_validate(role)
            for role in await self.repository.roles_in_event(event_id)
        ]

    async def role_records(self, user_id: UUID) -> list[RoleRecord]:
        return [
            RoleRecord.model_validate(role) for role in await self.repository.event_roles(user_id)
        ]

    async def role_page(
        self, event_id: UUID, role: str | None, q: str | None, limit: int, offset: int
    ) -> tuple[list[RoleRecord], int]:
        rows, total = await self.repository.role_page(event_id, role, q, limit, offset)
        return [RoleRecord.model_validate(row) for row in rows], total

    async def participant_counts(self, event_ids: list[UUID]) -> dict[UUID, int]:
        return await self.repository.participant_counts(event_ids)

    async def grant_role(self, user_id: UUID, event_id: UUID, role: str) -> RoleRecord:
        return RoleRecord.model_validate(await self.repository.add_role(user_id, event_id, role))

    async def revoke_role(self, role_id: UUID) -> None:
        await self.repository.delete_role(role_id)

    async def queue_email(self, recipient: str, subject: str, body: str) -> None:
        try:
            await run_in_threadpool(
                send_email.apply_async,
                args=[recipient, subject, body],
                argsrepr="(<redacted>,)",
                retry=False,
            )
        except Exception:
            raise ApiError(
                503, "EMAIL_QUEUE_UNAVAILABLE", "Change saved; email queue is unavailable"
            ) from None

    async def forgot_password(self, email: str) -> None:
        user = await self.repository.find_email(email, lock=True)
        if user is None or not user.is_active or not user.email_verified:
            return
        now = datetime.now(UTC)
        previous = await self.repository.last_reset(user.id)
        if previous:
            created = previous.created_at
            created = created.replace(tzinfo=UTC) if created.tzinfo is None else created
            if now - created < timedelta(seconds=60):
                return
        raw_token = token_urlsafe(32)
        await self.repository.add_reset(
            user.id, token_hash(raw_token), now, now + timedelta(hours=1)
        )
        await self.repository.commit()
        link = f"{str(self.settings.frontend_url).rstrip('/')}/reset-password?token={raw_token}"
        try:
            await run_in_threadpool(
                send_email.apply_async,
                args=[
                    email,
                    "SEAL - Reset your password",
                    f"Reset your password: {link}\nExpires in 1 hour.",
                ],
                argsrepr="(<redacted>,)",
                retry=False,
            )
        except Exception as exc:
            # Giữ cùng response cho email tồn tại và không tồn tại.
            logger.warning("Password reset enqueue failed: %s", type(exc).__name__)

    async def reset_password(self, data: ResetPasswordInput) -> None:
        hashed = await run_in_threadpool(password_hasher.hash, data.new_password)
        if not await self.repository.consume_reset(
            token_hash(data.token), datetime.now(UTC), hashed
        ):
            raise ApiError(400, "INVALID_TOKEN", "Invalid or expired reset token")
        await self.repository.commit()

    async def list_users(
        self, actor: UserOutput, q: str | None, limit: int, offset: int
    ) -> UserPage:
        self.require_admin(actor)
        users, total = await self.repository.list_users(q, limit, offset)
        return UserPage(items=[UserOutput.model_validate(user) for user in users], total=total)

    async def update_user(
        self, actor: UserOutput, user_id: UUID, data: AdminUserInput
    ) -> UserOutput:
        self.require_admin(actor)
        if user_id == actor.id and (data.is_admin is False or data.is_active is False):
            raise ApiError(
                403, "SELF_ADMIN_CHANGE", "Administrators cannot disable or demote themselves"
            )
        # Khóa theo UUID để các admin sửa chéo nhau không gây deadlock.
        locked = {}
        for identifier in sorted({actor.id, user_id}):
            locked[identifier] = await self.repository.get_user(identifier, lock=True)
        stored_actor = locked[actor.id]
        if stored_actor is None:
            raise ApiError(403, "FORBIDDEN", "Administrator access is required")
        self.require_admin(UserOutput.model_validate(stored_actor))
        user = locked[user_id]
        if user is None:
            raise ApiError(404, "USER_NOT_FOUND", "User does not exist")
        changes = {
            key: value
            for key, value in data.model_dump(exclude_unset=True).items()
            if getattr(user, key) != value
        }
        if changes:
            before = {key: getattr(user, key) for key in changes}
            await self.repository.update_profile(user, changes)
            if changes.get("is_active") is False:
                await self.repository.revoke_user_sessions(user.id)
            await self.write_audit_log(
                actor.id, "user.updated", "user", str(user.id), {"before": before, "after": changes}
            )
        output = UserOutput.model_validate(user)
        await self.repository.commit()
        return output

    async def write_audit_log(
        self, actor_id: UUID, action: str, target_type: str, target_id: str, data: dict[str, object]
    ) -> None:
        # Caller commit cùng nghiệp vụ; không commit riêng khiến audit lệch dữ liệu.
        await self.repository.write_audit_log(actor_id, action, target_type, target_id, data)

    async def list_audit_logs(
        self, actor: UserOutput, actor_id: UUID | None, action: str | None, limit: int, offset: int
    ) -> AuditLogPage:
        self.require_admin(actor)
        items, total = await self.repository.list_audit_logs(actor_id, action, limit, offset)
        return AuditLogPage(items=items, total=total)

    async def create_first_admin(self, data: RegisterInput) -> UserOutput:
        await self.repository.lock_admin_bootstrap()
        if await self.repository.has_admin():
            raise ApiError(409, "ADMIN_EXISTS", "An administrator already exists")
        hashed = await run_in_threadpool(password_hasher.hash, data.password)
        user = await self.repository.create_user(str(data.email), hashed, data.full_name)
        await self.repository.update_profile(user, {"is_admin": True, "email_verified": True})
        await self.write_audit_log(
            user.id,
            "admin.created",
            "user",
            str(user.id),
            {"after": {"is_admin": True, "is_active": True}},
        )
        output = UserOutput.model_validate(user)
        await self.repository.commit()
        return output
