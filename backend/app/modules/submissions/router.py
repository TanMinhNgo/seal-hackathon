from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Header

from app.core.dependencies import Limit, Offset, SubmissionServiceDependency, no_store
from app.core.schemas import Page
from app.modules.auth.dependencies import CurrentUser
from app.modules.submissions.schemas import (
    PresignInput,
    PresignOutput,
    RoundSubmission,
    SubmissionInput,
    SubmissionOutput,
)

router = APIRouter(prefix="/api/v1", tags=["submissions"], dependencies=[Depends(no_store)])


@router.post("/uploads/presign", response_model=PresignOutput)
async def presign(
    data: PresignInput, actor: CurrentUser, service: SubmissionServiceDependency
) -> PresignOutput:
    return await service.presign(actor, data)


@router.post(
    "/teams/{team_id}/rounds/{round_id}/submissions",
    status_code=201,
    response_model=SubmissionOutput,
)
async def submit(
    team_id: UUID,
    round_id: UUID,
    data: SubmissionInput,
    actor: CurrentUser,
    service: SubmissionServiceDependency,
    idempotency_key: Annotated[
        str, Header(min_length=1, max_length=128, pattern=r"^[\x21-\x7e]+$")
    ],
) -> SubmissionOutput:
    return await service.submit(actor, team_id, round_id, idempotency_key, data)


@router.get("/teams/{team_id}/rounds/{round_id}/submissions", response_model=Page[SubmissionOutput])
async def team_submissions(
    team_id: UUID,
    round_id: UUID,
    actor: CurrentUser,
    service: SubmissionServiceDependency,
    limit: Limit = 20,
    offset: Offset = 0,
) -> Page[SubmissionOutput]:
    return await service.list(actor, team_id, round_id, limit, offset)


@router.get("/submissions/{submission_id}", response_model=SubmissionOutput)
async def submission(
    submission_id: UUID, actor: CurrentUser, service: SubmissionServiceDependency
) -> SubmissionOutput:
    return await service.get(actor, submission_id)


@router.get(
    "/events/{event_id}/rounds/{round_id}/submissions", response_model=Page[RoundSubmission]
)
async def round_submissions(
    event_id: UUID,
    round_id: UUID,
    actor: CurrentUser,
    service: SubmissionServiceDependency,
    limit: Limit = 20,
    offset: Offset = 0,
) -> Page[RoundSubmission]:
    return await service.round_list(actor, event_id, round_id, limit, offset)
