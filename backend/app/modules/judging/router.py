from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Depends

from app.core.dependencies import JudgingServiceDependency, Limit, Offset, no_store
from app.core.schemas import Page
from app.modules.auth.dependencies import CurrentUser, OptionalUser, check_origin
from app.modules.auth.schemas import ErrorOutput
from app.modules.judging.schemas import (
    AnswerInput,
    AnswerOutput,
    AssignmentBatch,
    AssignmentDetail,
    AssignmentInput,
    AssignmentOutput,
    AutoInput,
    ConflictInput,
    ConflictOutput,
    EligibilityInput,
    JudgingProgress,
    Leaderboard,
    MentorAssignmentInput,
    MentorAssignmentOutput,
    MentorBatch,
    NoteInput,
    NoteOutput,
    QuestionInput,
    QuestionOutput,
    ReasonInput,
    RevisionInput,
    RoundTeam,
    Rubric,
    RubricInput,
    ScoresInput,
    ScoresOutput,
    TeamResult,
)
from app.modules.teams.schemas import TeamOutput

router = APIRouter(
    prefix="/api/v1",
    tags=["judging"],
    dependencies=[Depends(check_origin), Depends(no_store)],
    responses={s: {"model": ErrorOutput} for s in (401, 403, 404, 409, 422, 429, 503)},
)
ROUND = "/events/{event_id}/rounds/{round_id}"


@router.get(ROUND + "/rubric", response_model=Rubric)
async def rubric(
    event_id: UUID, round_id: UUID, service: JudgingServiceDependency, user: OptionalUser
) -> Rubric:
    return await service.rubric(user, event_id, round_id)


@router.put(ROUND + "/rubric", response_model=Rubric)
async def put_rubric(
    event_id: UUID,
    round_id: UUID,
    data: RubricInput,
    service: JudgingServiceDependency,
    user: CurrentUser,
) -> Rubric:
    return await service.put_rubric(user, event_id, round_id, data)


@router.post("/events/{event_id}/conflicts", response_model=ConflictOutput, status_code=201)
async def conflict(
    event_id: UUID, data: ConflictInput, service: JudgingServiceDependency, user: CurrentUser
) -> ConflictOutput:
    return await service.declare_conflict(user, event_id, data)


@router.get("/events/{event_id}/conflicts", response_model=Page[ConflictOutput])
async def conflicts(
    event_id: UUID,
    service: JudgingServiceDependency,
    user: CurrentUser,
    limit: Limit = 20,
    offset: Offset = 0,
) -> Page[ConflictOutput]:
    return await service.conflicts(user, event_id, limit, offset)


@router.get(ROUND + "/assignments", response_model=Page[AssignmentOutput])
async def assignments(
    event_id: UUID,
    round_id: UUID,
    service: JudgingServiceDependency,
    user: CurrentUser,
    limit: Limit = 20,
    offset: Offset = 0,
) -> Page[AssignmentOutput]:
    return await service.assignments(user, event_id, round_id, limit, offset)


@router.post(ROUND + "/assignments", response_model=AssignmentBatch)
async def assign(
    event_id: UUID,
    round_id: UUID,
    data: AssignmentInput,
    service: JudgingServiceDependency,
    user: CurrentUser,
) -> AssignmentBatch:
    return await service.assign(user, event_id, round_id, data)


@router.post(ROUND + "/assignments/auto", response_model=AssignmentBatch)
async def auto_assign(
    event_id: UUID,
    round_id: UUID,
    data: AutoInput,
    service: JudgingServiceDependency,
    user: CurrentUser,
) -> AssignmentBatch:
    return await service.assign(user, event_id, round_id, data, auto=True)


@router.delete("/assignments/{assignment_id}", status_code=204)
async def delete_assignment(
    assignment_id: UUID, service: JudgingServiceDependency, user: CurrentUser
) -> None:
    await service.change_assignment(user, assignment_id, "delete")


@router.post("/assignments/{assignment_id}/cancel", response_model=AssignmentOutput)
async def cancel_assignment(
    assignment_id: UUID, data: ReasonInput, service: JudgingServiceDependency, user: CurrentUser
) -> AssignmentOutput:
    return await service.change_assignment(user, assignment_id, "cancel", data.reason)


@router.post("/assignments/{assignment_id}/reopen", response_model=AssignmentOutput)
async def reopen_assignment(
    assignment_id: UUID, data: ReasonInput, service: JudgingServiceDependency, user: CurrentUser
) -> AssignmentOutput:
    return await service.change_assignment(user, assignment_id, "reopen", data.reason)


@router.get("/me/assignments", response_model=Page[AssignmentOutput])
async def my_assignments(
    service: JudgingServiceDependency,
    user: CurrentUser,
    event_id: UUID | None = None,
    round_id: UUID | None = None,
    limit: Limit = 20,
    offset: Offset = 0,
) -> Page[AssignmentOutput]:
    return await service.assignments(user, event_id, round_id, limit, offset, mine=True)


@router.get("/assignments/{assignment_id}", response_model=AssignmentDetail)
async def assignment_detail(
    assignment_id: UUID, service: JudgingServiceDependency, user: CurrentUser
) -> AssignmentDetail:
    return await service.detail(user, assignment_id)


@router.put("/assignments/{assignment_id}/scores", response_model=ScoresOutput)
async def scores(
    assignment_id: UUID, data: ScoresInput, service: JudgingServiceDependency, user: CurrentUser
) -> ScoresOutput:
    return await service.write_scores(user, assignment_id, data)


@router.post("/assignments/{assignment_id}/submit", response_model=AssignmentOutput)
async def submit_scores(
    assignment_id: UUID, data: RevisionInput, service: JudgingServiceDependency, user: CurrentUser
) -> AssignmentOutput:
    return await service.write_scores(user, assignment_id, data, submit=True)


@router.get(ROUND + "/eligible-teams", response_model=Page[RoundTeam])
async def eligible_teams(
    event_id: UUID,
    round_id: UUID,
    service: JudgingServiceDependency,
    user: CurrentUser,
    limit: Limit = 20,
    offset: Offset = 0,
) -> Page[RoundTeam]:
    return await service.eligible_page(user, event_id, round_id, limit, offset)


@router.put(ROUND + "/eligible-teams", response_model=Page[RoundTeam])
async def put_eligible(
    event_id: UUID,
    round_id: UUID,
    data: EligibilityInput,
    service: JudgingServiceDependency,
    user: CurrentUser,
) -> Page[RoundTeam]:
    return await service.put_eligible(user, event_id, round_id, data)


@router.get(ROUND + "/judging-progress", response_model=JudgingProgress)
async def progress(
    event_id: UUID,
    round_id: UUID,
    service: JudgingServiceDependency,
    user: CurrentUser,
    limit: Limit = 20,
    offset: Offset = 0,
) -> JudgingProgress:
    return await service.progress(user, event_id, round_id, limit, offset)


@router.post(ROUND + "/lock", status_code=204)
async def lock(
    event_id: UUID, round_id: UUID, service: JudgingServiceDependency, user: CurrentUser
) -> None:
    await service.change_round(user, event_id, round_id, "lock")


@router.post(ROUND + "/unlock", status_code=204)
async def unlock(
    event_id: UUID,
    round_id: UUID,
    data: ReasonInput,
    service: JudgingServiceDependency,
    user: CurrentUser,
) -> None:
    await service.change_round(user, event_id, round_id, "unlock", data.reason)


@router.post(ROUND + "/publish", status_code=204)
async def publish(
    event_id: UUID, round_id: UUID, service: JudgingServiceDependency, user: CurrentUser
) -> None:
    await service.change_round(user, event_id, round_id, "publish")


@router.post(ROUND + "/unpublish", status_code=204)
async def unpublish(
    event_id: UUID,
    round_id: UUID,
    data: ReasonInput,
    service: JudgingServiceDependency,
    user: CurrentUser,
) -> None:
    await service.change_round(user, event_id, round_id, "unpublish", data.reason)


@router.get(ROUND + "/leaderboard", response_model=Leaderboard)
async def leaderboard(
    event_id: UUID,
    round_id: UUID,
    service: JudgingServiceDependency,
    user: OptionalUser,
    track_id: UUID | None = None,
    limit: Limit = 20,
    offset: Offset = 0,
) -> Leaderboard:
    return await service.leaderboard(user, event_id, round_id, track_id, limit, offset)


@router.get("/teams/{team_id}/rounds/{round_id}/result", response_model=TeamResult)
async def result(
    team_id: UUID, round_id: UUID, service: JudgingServiceDependency, user: CurrentUser
) -> TeamResult:
    return await service.result(user, team_id, round_id)


@router.post("/events/{event_id}/mentor-assignments", response_model=MentorBatch, status_code=201)
async def assign_mentor(
    event_id: UUID,
    data: MentorAssignmentInput,
    service: JudgingServiceDependency,
    user: CurrentUser,
) -> MentorBatch:
    return await service.assign_mentor(user, event_id, data)


@router.get("/events/{event_id}/mentor-assignments", response_model=Page[MentorAssignmentOutput])
async def mentor_assignments(
    event_id: UUID,
    service: JudgingServiceDependency,
    user: CurrentUser,
    limit: Limit = 20,
    offset: Offset = 0,
) -> Page[MentorAssignmentOutput]:
    return await service.mentor_assignments(user, event_id, limit, offset)


@router.delete("/mentor-assignments/{assignment_id}", status_code=204)
async def revoke_mentor(
    assignment_id: UUID, service: JudgingServiceDependency, user: CurrentUser
) -> None:
    await service.revoke_mentor(user, assignment_id)


@router.get("/me/mentoring", response_model=Page[TeamOutput])
async def mentoring(
    service: JudgingServiceDependency,
    user: CurrentUser,
    event_id: UUID | None = None,
    limit: Limit = 20,
    offset: Offset = 0,
) -> Page[TeamOutput]:
    return await service.mentoring(user, event_id, limit, offset)


@router.get("/teams/{team_id}/mentor-notes", response_model=Page[NoteOutput])
async def notes(
    team_id: UUID,
    service: JudgingServiceDependency,
    user: CurrentUser,
    commit_sha: str | None = None,
    limit: Limit = 20,
    offset: Offset = 0,
) -> Page[NoteOutput]:
    return await service.notes(user, team_id, commit_sha, limit, offset)


@router.post("/teams/{team_id}/mentor-notes", response_model=NoteOutput, status_code=201)
async def add_note(
    team_id: UUID, data: NoteInput, service: JudgingServiceDependency, user: CurrentUser
) -> NoteOutput:
    return await service.add_note(user, team_id, data)


@router.get("/teams/{team_id}/questions", response_model=Page[QuestionOutput])
async def questions(
    team_id: UUID,
    service: JudgingServiceDependency,
    user: CurrentUser,
    status: Literal["open", "answered", "resolved"] | None = None,
    limit: Limit = 20,
    offset: Offset = 0,
) -> Page[QuestionOutput]:
    return await service.questions(user, team_id, status, limit, offset)


@router.post("/teams/{team_id}/questions", response_model=QuestionOutput, status_code=201)
async def ask(
    team_id: UUID, data: QuestionInput, service: JudgingServiceDependency, user: CurrentUser
) -> QuestionOutput:
    return await service.ask(user, team_id, data)


@router.get("/questions/{question_id}/answers", response_model=Page[AnswerOutput])
async def answers(
    question_id: UUID,
    service: JudgingServiceDependency,
    user: CurrentUser,
    limit: Limit = 20,
    offset: Offset = 0,
) -> Page[AnswerOutput]:
    return await service.answers(user, question_id, limit, offset)


@router.post("/questions/{question_id}/answers", response_model=AnswerOutput, status_code=201)
async def answer(
    question_id: UUID, data: AnswerInput, service: JudgingServiceDependency, user: CurrentUser
) -> AnswerOutput:
    return await service.answer(user, question_id, data)


@router.post("/questions/{question_id}/resolve", status_code=204)
async def resolve(question_id: UUID, service: JudgingServiceDependency, user: CurrentUser) -> None:
    await service.resolve(user, question_id)
