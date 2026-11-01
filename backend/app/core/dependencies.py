from typing import Annotated

from fastapi import Depends, Query, Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_db
from app.modules.auth.dependencies import ServiceDependency, SettingsDependency
from app.modules.commits.repository import CommitRepository
from app.modules.commits.service import CommitService
from app.modules.events.repository import EventRepository
from app.modules.events.service import EventService
from app.modules.judging.repository import JudgingRepository
from app.modules.judging.service import JudgingService
from app.modules.submissions.repository import SubmissionRepository
from app.modules.submissions.service import SubmissionService
from app.modules.teams.repository import TeamRepository
from app.modules.teams.service import TeamService

SessionDependency = Annotated[AsyncSession, Depends(get_db)]
Limit = Annotated[int, Query(ge=1, le=100)]
Offset = Annotated[int, Query(ge=0)]
Search = Annotated[str | None, Query(max_length=100)]


def no_store(response: Response) -> None:
    response.headers["Cache-Control"] = "no-store"


def get_event_service(session: SessionDependency, auth: ServiceDependency) -> EventService:
    return EventService(EventRepository(session), auth, JudgingService(JudgingRepository(session)))


EventServiceDependency = Annotated[EventService, Depends(get_event_service)]


def get_team_service(
    session: SessionDependency,
    events: EventServiceDependency,
    auth: ServiceDependency,
    settings: SettingsDependency,
) -> TeamService:
    return TeamService(
        TeamRepository(session), events, auth, settings, JudgingService(JudgingRepository(session))
    )


TeamServiceDependency = Annotated[TeamService, Depends(get_team_service)]


def get_submission_service(
    session: SessionDependency,
    teams: TeamServiceDependency,
    events: EventServiceDependency,
    auth: ServiceDependency,
    settings: SettingsDependency,
) -> SubmissionService:
    return SubmissionService(
        SubmissionRepository(session),
        teams,
        events,
        auth,
        JudgingService(JudgingRepository(session)),
        settings,
    )


SubmissionServiceDependency = Annotated[SubmissionService, Depends(get_submission_service)]


def get_judging_service(
    session: SessionDependency,
    teams: TeamServiceDependency,
    events: EventServiceDependency,
    auth: ServiceDependency,
    settings: SettingsDependency,
    submissions: SubmissionServiceDependency,
) -> JudgingService:
    return JudgingService(
        JudgingRepository(session),
        teams,
        events,
        auth,
        settings,
        submissions,
        CommitService(CommitRepository(session)),
    )


JudgingServiceDependency = Annotated[JudgingService, Depends(get_judging_service)]
