from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Cookie, Depends, Query, Response

from app.core.dependencies import EventServiceDependency
from app.core.security import REFRESH_TTL
from app.modules.auth.dependencies import (
    AdminUser,
    CurrentUser,
    ServiceDependency,
    SettingsDependency,
    SystemServiceDependency,
    check_origin,
    rate_limit_auth,
)
from app.modules.auth.schemas import (
    AdminUserInput,
    AuditLogPage,
    EmailInput,
    ErrorOutput,
    EventRoleOutput,
    LoginInput,
    ProfileInput,
    RegisterInput,
    ResetPasswordInput,
    SystemOverview,
    TokenOutput,
    UserOutput,
    UserPage,
    VerifyEmailInput,
)

responses = {status: {"model": ErrorOutput} for status in (400, 401, 403, 404, 409, 422, 429, 503)}
auth_router = APIRouter(
    prefix="/api/v1/auth",
    tags=["auth"],
    dependencies=[Depends(check_origin), Depends(rate_limit_auth)],
    responses=responses,
)
users_router = APIRouter(prefix="/api/v1/users", tags=["users"], responses=responses)
admin_router = APIRouter(
    prefix="/api/v1/admin",
    tags=["admin"],
    responses=responses,
    dependencies=[Depends(check_origin)],
)
RefreshCookie = Annotated[str | None, Cookie(alias="refresh_token", max_length=4096)]


def set_refresh_cookie(response: Response, refresh: str, secure: bool) -> None:
    response.set_cookie(
        "refresh_token",
        refresh,
        max_age=int(REFRESH_TTL.total_seconds()),
        httponly=True,
        secure=secure,
        samesite="lax",
        path="/api/v1/auth",
    )
    response.headers["Cache-Control"] = "no-store"
    response.headers["Pragma"] = "no-cache"


@auth_router.post("/register", response_model=UserOutput, status_code=201)
async def register(data: RegisterInput, service: ServiceDependency) -> UserOutput:
    return await service.register(data)


@auth_router.post("/verify-email", status_code=204)
async def verify_email(data: VerifyEmailInput, service: ServiceDependency) -> None:
    await service.verify_email(data.token)


@auth_router.post("/resend-verification", status_code=204)
async def resend_verification(data: EmailInput, service: ServiceDependency) -> None:
    await service.resend_verification(str(data.email))


@auth_router.post("/forgot-password", status_code=204)
async def forgot_password(data: EmailInput, service: ServiceDependency) -> None:
    await service.forgot_password(str(data.email))


@auth_router.post("/reset-password", status_code=204)
async def reset_password(data: ResetPasswordInput, service: ServiceDependency) -> None:
    await service.reset_password(data)


@auth_router.post("/login", response_model=TokenOutput)
async def login(
    data: LoginInput, response: Response, service: ServiceDependency, settings: SettingsDependency
) -> TokenOutput:
    access, refresh = await service.login(data)
    set_refresh_cookie(response, refresh, settings.frontend_url.scheme == "https")
    return TokenOutput(access_token=access)


@auth_router.post("/refresh", response_model=TokenOutput)
async def refresh_token(
    response: Response,
    service: ServiceDependency,
    settings: SettingsDependency,
    refresh: RefreshCookie = None,
) -> TokenOutput:
    access, token = await service.refresh(refresh or "")
    set_refresh_cookie(response, token, settings.frontend_url.scheme == "https")
    return TokenOutput(access_token=access)


@auth_router.post("/logout", status_code=204)
async def logout(
    response: Response, service: ServiceDependency, refresh: RefreshCookie = None
) -> None:
    await service.logout(refresh)
    response.delete_cookie("refresh_token", path="/api/v1/auth", httponly=True, samesite="lax")
    response.headers["Cache-Control"] = "no-store"


@users_router.get("/me", response_model=UserOutput)
async def get_me(user: CurrentUser, response: Response) -> UserOutput:
    response.headers["Cache-Control"] = "no-store"
    return user


@users_router.patch("/me", response_model=UserOutput)
async def update_me(
    data: ProfileInput, user: CurrentUser, service: ServiceDependency, response: Response
) -> UserOutput:
    response.headers["Cache-Control"] = "no-store"
    return await service.update_profile(user, data)


@users_router.get("/me/event-roles", response_model=list[EventRoleOutput])
async def event_roles(
    user: CurrentUser, service: ServiceDependency, response: Response
) -> list[EventRoleOutput]:
    response.headers["Cache-Control"] = "no-store"
    return await service.event_roles(user)


@admin_router.get("/users", response_model=UserPage)
async def list_users(
    user: AdminUser,
    service: ServiceDependency,
    response: Response,
    q: Annotated[str | None, Query(max_length=100)] = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> UserPage:
    response.headers["Cache-Control"] = "no-store"
    return await service.list_users(user, q, limit, offset)


@admin_router.patch("/users/{user_id}", response_model=UserOutput)
async def update_user(
    user_id: UUID,
    data: AdminUserInput,
    user: AdminUser,
    service: EventServiceDependency,
    response: Response,
) -> UserOutput:
    response.headers["Cache-Control"] = "no-store"
    return await service.update_account(user, user_id, data)


@admin_router.get("/audit-logs", response_model=AuditLogPage)
async def list_audit_logs(
    user: AdminUser,
    service: ServiceDependency,
    response: Response,
    actor_id: UUID | None = None,
    action: Annotated[str | None, Query(max_length=100)] = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> AuditLogPage:
    response.headers["Cache-Control"] = "no-store"
    return await service.list_audit_logs(user, actor_id, action, limit, offset)


@admin_router.get("/system", response_model=SystemOverview)
async def system_overview(
    user: AdminUser, service: SystemServiceDependency, response: Response
) -> SystemOverview:
    response.headers["Cache-Control"] = "no-store"
    return await service.overview(user)
