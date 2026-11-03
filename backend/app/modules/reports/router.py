from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Response

from app.core.dependencies import (
    EventServiceDependency,
    JudgingServiceDependency,
    SessionDependency,
    no_store,
)
from app.modules.auth.dependencies import CurrentUser
from app.modules.reports.repository import ReportRepository
from app.modules.reports.schemas import Dashboard, ReportFormat, ReportType
from app.modules.reports.service import ReportService


def get_report_service(
    session: SessionDependency, events: EventServiceDependency, judging: JudgingServiceDependency
) -> ReportService:
    return ReportService(ReportRepository(session), events, judging)


Service = Annotated[ReportService, Depends(get_report_service)]
router = APIRouter(prefix="/api/v1/events", tags=["reports"], dependencies=[Depends(no_store)])


@router.get("/{event_id}/dashboard", response_model=Dashboard)
async def dashboard(event_id: UUID, service: Service, user: CurrentUser) -> Dashboard:
    return await service.dashboard(user, event_id)


@router.get(
    "/{event_id}/reports/export",
    responses={
        200: {
            "content": {
                "application/pdf": {},
                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet": {},
            }
        }
    },
)
async def export(
    event_id: UUID,
    type: ReportType,
    format: ReportFormat,
    service: Service,
    user: CurrentUser,
    round_id: UUID | None = None,
    track_id: UUID | None = None,
) -> Response:
    data = await service.export(user, event_id, type, format, round_id, track_id)
    media = (
        "application/pdf"
        if format == "pdf"
        else "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )
    return Response(
        data,
        media_type=media,
        headers={
            "Content-Disposition": f'attachment; filename="{type}.{format}"',
            "Cache-Control": "no-store",
            "X-Content-Type-Options": "nosniff",
        },
    )
