from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Depends

from app.core.dependencies import Limit, Offset, Search, TeamServiceDependency, no_store
from app.core.schemas import Page
from app.modules.auth.dependencies import CurrentUser, OptionalUser, check_origin
from app.modules.auth.schemas import EmailInput, ErrorOutput
from app.modules.teams.schemas import (
    InviteInput,
    InviteOutput,
    MyEvent,
    PublicTeam,
    QueueOutput,
    RepoInput,
    ReviewInput,
    TeamBrief,
    TeamCreate,
    TeamOutput,
    TeamPatch,
    TransferInput,
)

router = APIRouter(
    prefix="/api/v1",
    tags=["teams"],
    dependencies=[Depends(check_origin), Depends(no_store)],
    responses={
        status: {"model": ErrorOutput} for status in (400, 401, 403, 404, 409, 422, 429, 503)
    },
)


@router.get("/me/events", response_model=Page[MyEvent])
async def my_events(
    service: TeamServiceDependency, user: CurrentUser, limit: Limit = 20, offset: Offset = 0
) -> Page[MyEvent]:
    return await service.my_events(user, limit, offset)


@router.get("/events/{event_id}/team-directory", response_model=Page[TeamBrief])
async def directory(
    event_id: UUID,
    service: TeamServiceDependency,
    user: CurrentUser,
    q: Search = None,
    limit: Limit = 20,
    offset: Offset = 0,
) -> Page[TeamBrief]:
    return await service.directory(user, event_id, q, limit, offset)


@router.get("/events/{event_id}/teams/me", response_model=TeamOutput)
async def my_team(event_id: UUID, service: TeamServiceDependency, user: CurrentUser) -> TeamOutput:
    return await service.own(user, event_id)


@router.get(
    "/events/{event_id}/teams/public",
    response_model=list[PublicTeam],
    openapi_extra={"security": [{}]},
)
async def public_teams(
    event_id: UUID, service: TeamServiceDependency, user: OptionalUser
) -> list[PublicTeam]:
    return await service.public(user, event_id)


@router.get("/events/{event_id}/teams", response_model=Page[TeamOutput])
async def teams(
    event_id: UUID,
    service: TeamServiceDependency,
    user: CurrentUser,
    status: Literal["pending", "approved", "rejected"] | None = None,
    track_id: UUID | None = None,
    q: Search = None,
    limit: Limit = 20,
    offset: Offset = 0,
) -> Page[TeamOutput]:
    return await service.list(user, event_id, status, track_id, q, limit, offset)


@router.post(
    "/events/{event_id}/teams",
    response_model=TeamOutput,
    status_code=201,
)
async def create_team(
    event_id: UUID, data: TeamCreate, service: TeamServiceDependency, user: CurrentUser
) -> TeamOutput:
    return await service.create(user, event_id, data)


@router.post("/teams/join", response_model=TeamOutput)
async def join_team(
    data: InviteInput, service: TeamServiceDependency, user: CurrentUser
) -> TeamOutput:
    return await service.join(user, data.invite_code)


@router.get("/teams/{team_id}", response_model=TeamOutput)
async def team(team_id: UUID, service: TeamServiceDependency, user: CurrentUser) -> TeamOutput:
    return await service.view(user, team_id)


@router.patch("/teams/{team_id}", response_model=TeamOutput)
async def update_team(
    team_id: UUID, data: TeamPatch, service: TeamServiceDependency, user: CurrentUser
) -> TeamOutput:
    return await service.update(user, team_id, data)


@router.post("/teams/{team_id}/invite-code", response_model=InviteOutput)
async def rotate_invite(
    team_id: UUID, service: TeamServiceDependency, user: CurrentUser
) -> InviteOutput:
    return InviteOutput(invite_code=await service.invite_code(user, team_id))


@router.post("/teams/{team_id}/invitations", response_model=QueueOutput, status_code=202)
async def invite(
    team_id: UUID, data: EmailInput, service: TeamServiceDependency, user: CurrentUser
) -> QueueOutput:
    await service.invitation(user, team_id, str(data.email))
    return QueueOutput()


@router.post(
    "/teams/{team_id}/members/{user_id}/approve",
    response_model=TeamOutput,
)
async def approve_member(
    team_id: UUID, user_id: UUID, service: TeamServiceDependency, user: CurrentUser
) -> TeamOutput:
    return await service.approve_member(user, team_id, user_id)


@router.delete("/teams/{team_id}/members/{user_id}", status_code=204)
async def remove_member(
    team_id: UUID, user_id: UUID, service: TeamServiceDependency, user: CurrentUser
) -> None:
    await service.remove_member(user, team_id, user_id)


@router.post("/teams/{team_id}/transfer-leader", response_model=TeamOutput)
async def transfer_leader(
    team_id: UUID, data: TransferInput, service: TeamServiceDependency, user: CurrentUser
) -> TeamOutput:
    return await service.transfer(user, team_id, data.user_id)


@router.put("/teams/{team_id}/repo", response_model=TeamOutput)
async def repo(
    team_id: UUID, data: RepoInput, service: TeamServiceDependency, user: CurrentUser
) -> TeamOutput:
    return await service.repo(user, team_id, data.repo_url)


@router.post("/teams/{team_id}/review", response_model=TeamOutput)
async def review(
    team_id: UUID, data: ReviewInput, service: TeamServiceDependency, user: CurrentUser
) -> TeamOutput:
    return await service.review(user, team_id, data)
