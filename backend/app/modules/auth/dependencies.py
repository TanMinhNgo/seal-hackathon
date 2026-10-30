from collections.abc import Callable, Coroutine
from typing import Annotated
from uuid import UUID

from fastapi import Depends, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from redis.asyncio import Redis
from redis.exceptions import RedisError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings, get_settings
from app.core.db import get_db
from app.core.errors import ApiError
from app.modules.auth.repository import AuthRepository
from app.modules.auth.schemas import Role, UserOutput
from app.modules.auth.service import AuthService
from app.modules.auth.system_service import SystemService

SettingsDependency = Annotated[Settings, Depends(get_settings)]


def get_auth_service(
    session: Annotated[AsyncSession, Depends(get_db)], settings: SettingsDependency
) -> AuthService:
    return AuthService(AuthRepository(session), settings)


ServiceDependency = Annotated[AuthService, Depends(get_auth_service)]


def get_system_service(
    session: Annotated[AsyncSession, Depends(get_db)], settings: SettingsDependency
) -> SystemService:
    return SystemService(AuthRepository(session), settings)


SystemServiceDependency = Annotated[SystemService, Depends(get_system_service)]
bearer = HTTPBearer(auto_error=False)


async def get_current_user(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer)],
    service: ServiceDependency,
) -> UserOutput:
    if credentials is None:
        raise ApiError(401, "INVALID_TOKEN", "Bearer token is required")
    return await service.current_user(credentials.credentials)


CurrentUser = Annotated[UserOutput, Depends(get_current_user)]


async def get_optional_user(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer)],
    service: ServiceDependency,
) -> UserOutput | None:
    return await service.current_user(credentials.credentials) if credentials else None


OptionalUser = Annotated[UserOutput | None, Depends(get_optional_user)]


async def require_admin(user: CurrentUser, service: ServiceDependency) -> UserOutput:
    service.require_admin(user)
    return user


AdminUser = Annotated[UserOutput, Depends(require_admin)]


def require_event_role(*roles: Role) -> Callable[..., Coroutine[object, object, UserOutput]]:
    async def check(event_id: UUID, user: CurrentUser, service: ServiceDependency) -> UserOutput:
        await service.require_event_role(user, event_id, roles)
        return user

    return check


def check_origin(request: Request, settings: SettingsDependency) -> None:
    origin = request.headers.get("origin")
    if origin is not None and origin not in settings.cors_origins:
        raise ApiError(403, "UNTRUSTED_ORIGIN", "Origin is not allowed")


async def rate_limit_auth(request: Request, settings: SettingsDependency) -> None:
    # Không tin X-Forwarded-For khi chưa cấu hình reverse proxy đáng tin cậy.
    address = request.client.host if request.client else "unknown"
    try:
        async with Redis.from_url(
            str(settings.redis_url), socket_connect_timeout=2, socket_timeout=2
        ) as redis:
            count = await redis.eval(
                "local n = redis.call('INCR', KEYS[1]); "
                "if n == 1 then redis.call('EXPIRE', KEYS[1], 60) end; return n",
                1,
                f"seal:auth:rate:{address}",
            )
    except RedisError:
        raise ApiError(
            503, "RATE_LIMIT_UNAVAILABLE", "Authentication is temporarily unavailable"
        ) from None
    if count > 30:
        raise ApiError(429, "RATE_LIMITED", "Too many requests; try again in one minute")
