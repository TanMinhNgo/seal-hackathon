from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Path

from app.core.dependencies import (
    EventServiceDependency,
    Limit,
    Offset,
    SessionDependency,
    TeamServiceDependency,
    no_store,
)
from app.core.schemas import Page
from app.modules.auth.dependencies import CurrentUser
from app.modules.commits.repository import CommitRepository
from app.modules.commits.schemas import (
    CommitOutput,
    CommitOverview,
    CommitStats,
    DiffPage,
    SyncQueued,
)
from app.modules.commits.service import CommitService


def get_commit_service(
    session: SessionDependency, teams: TeamServiceDependency, events: EventServiceDependency
) -> CommitService:
    return CommitService(CommitRepository(session), teams, events)


Service = Annotated[CommitService, Depends(get_commit_service)]
Sha = Annotated[str, Path(pattern=r"^[0-9a-f]{40}$")]
router = APIRouter(prefix="/api/v1", tags=["commits"], dependencies=[Depends(no_store)])


@router.get("/teams/{team_id}/commits", response_model=Page[CommitOutput])
async def commits(
    team_id: UUID, service: Service, user: CurrentUser, limit: Limit = 20, offset: Offset = 0
) -> Page[CommitOutput]:
    return await service.page(user, team_id, limit, offset)


@router.get("/teams/{team_id}/commits/{sha}", response_model=CommitOutput)
async def commit(team_id: UUID, sha: Sha, service: Service, user: CurrentUser) -> CommitOutput:
    return await service.detail(user, team_id, sha)


@router.get("/teams/{team_id}/commits/{sha}/diff", response_model=DiffPage)
async def diff(
    team_id: UUID,
    sha: Sha,
    service: Service,
    user: CurrentUser,
    limit: Limit = 20,
    offset: Offset = 0,
) -> DiffPage:
    return await service.diff(user, team_id, sha, limit, offset)


@router.get("/teams/{team_id}/commit-stats", response_model=CommitStats)
async def stats(team_id: UUID, service: Service, user: CurrentUser) -> CommitStats:
    return await service.stats(user, team_id)


@router.get("/events/{event_id}/commit-overview", response_model=Page[CommitOverview])
async def overview(
    event_id: UUID, service: Service, user: CurrentUser, limit: Limit = 20, offset: Offset = 0
) -> Page[CommitOverview]:
    return await service.overview(user, event_id, limit, offset)


@router.post("/teams/{team_id}/sync", status_code=202, response_model=SyncQueued)
async def sync(team_id: UUID, service: Service, user: CurrentUser) -> SyncQueued:
    return await service.sync(user, team_id)
