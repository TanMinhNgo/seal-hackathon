from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query

from app.core.dependencies import (
    EventServiceDependency,
    JudgingServiceDependency,
    Limit,
    Offset,
    SessionDependency,
    TeamServiceDependency,
    no_store,
)
from app.core.schemas import Page
from app.modules.ai_reviews.repository import ReviewRepository
from app.modules.ai_reviews.schemas import (
    AiSummary,
    FlagInput,
    FlagOutput,
    ResolveInput,
    RetryInput,
    RetryOutput,
    ReviewOutput,
    Verdict,
)
from app.modules.ai_reviews.service import ReviewService
from app.modules.auth.dependencies import CurrentUser, ServiceDependency, check_origin
from app.modules.commits.router import Service as CommitServiceDependency


def get_review_service(
    session: SessionDependency,
    commits: CommitServiceDependency,
    teams: TeamServiceDependency,
    events: EventServiceDependency,
    judging: JudgingServiceDependency,
    auth: ServiceDependency,
) -> ReviewService:
    return ReviewService(ReviewRepository(session), commits, teams, events, judging, auth)


Service = Annotated[ReviewService, Depends(get_review_service)]
router = APIRouter(
    prefix="/api/v1", tags=["ai-reviews"], dependencies=[Depends(no_store), Depends(check_origin)]
)


@router.get("/teams/{team_id}/ai-reviews", response_model=Page[ReviewOutput])
async def reviews(
    team_id: UUID,
    service: Service,
    user: CurrentUser,
    round_id: UUID | None = None,
    verdict: Verdict | None = None,
    commit_sha: Annotated[str | None, Query(pattern=r"^[0-9a-f]{40}$")] = None,
    limit: Limit = 20,
    offset: Offset = 0,
) -> Page[ReviewOutput]:
    return await service.page(user, team_id, round_id, verdict, commit_sha, limit, offset)


@router.get(
    "/teams/{team_id}/ai-summary", response_model=AiSummary, response_model_exclude_unset=True
)
async def summary(
    team_id: UUID, service: Service, user: CurrentUser, round_id: UUID | None = None
) -> AiSummary:
    return await service.summary(user, team_id, round_id)


@router.post("/ai-reviews/{review_id}/flag", status_code=204)
async def flag(review_id: UUID, data: FlagInput, service: Service, user: CurrentUser) -> None:
    await service.flag(user, review_id, data.reason)


@router.get("/ai-reviews/{review_id}/flags", response_model=Page[FlagOutput])
async def flags(
    review_id: UUID, service: Service, user: CurrentUser, limit: Limit = 20, offset: Offset = 0
) -> Page[FlagOutput]:
    return await service.flags(user, review_id, limit, offset)


@router.post("/ai-review-flags/{flag_id}/resolve", response_model=FlagOutput)
async def resolve(
    flag_id: UUID, data: ResolveInput, service: Service, user: CurrentUser
) -> FlagOutput:
    return await service.resolve(user, flag_id, data.decision, data.note)


@router.post("/teams/{team_id}/ai-reviews/retry", response_model=RetryOutput, status_code=202)
async def retry(
    team_id: UUID, data: RetryInput, service: Service, user: CurrentUser
) -> RetryOutput:
    return await service.retry(user, team_id, data.job_id)
