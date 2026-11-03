from uuid import UUID

from app.core.errors import ApiError
from app.integrations.report_files import render
from app.modules.reports.schemas import Dashboard


class ReportService:
    def __init__(self, repository: object, events: object, judging: object) -> None:
        self.repository = repository
        self.events = events
        self.judging = judging

    async def dashboard(self, actor: object, event_id: UUID) -> Dashboard:
        await self.events.get(event_id)
        await self.events.require_organizer(actor, event_id)
        return Dashboard(**await self.repository.dashboard(event_id))

    async def export(
        self,
        actor: object,
        event_id: UUID,
        kind: str,
        format_: str,
        round_id: UUID | None,
        track_id: UUID | None,
    ) -> bytes:
        await self.events.get(event_id)
        await self.events.require_organizer(actor, event_id, admin_read=True)
        await self.events.ensure_track(event_id, track_id)
        if round_id:
            await self.events.submission_round(event_id, round_id)
        if kind == "leaderboard":
            if round_id is None:
                raise ApiError(422, "ROUND_REQUIRED", "Leaderboard export requires round_id")
            rows = await self.judging.export_leaderboard(actor, event_id, round_id, track_id)
        else:
            rows = await self.repository.rows(event_id, kind, round_id, track_id)
        if len(rows) > 10000:
            raise ApiError(422, "EXPORT_TOO_LARGE", "Narrow the round or track filter")
        from fastapi.concurrency import run_in_threadpool

        return await run_in_threadpool(render, kind, format_, rows)
