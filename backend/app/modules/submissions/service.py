import hashlib
import json
import logging
from datetime import UTC, datetime
from pathlib import PurePosixPath
from uuid import UUID, uuid4

from starlette.concurrency import run_in_threadpool

from app.core.config import Settings
from app.core.errors import ApiError
from app.core.schemas import Page, utc
from app.integrations import github_client, storage
from app.modules.auth.schemas import UserOutput
from app.modules.auth.service import AuthService
from app.modules.events.service import EventService
from app.modules.judging.service import JudgingService
from app.modules.submissions.models import Submission
from app.modules.submissions.repository import SubmissionRepository
from app.modules.submissions.schemas import (
    FileOutput,
    PresignInput,
    PresignOutput,
    RoundSubmission,
    SubmissionInput,
    SubmissionOutput,
)
from app.modules.teams.service import TeamService

logger = logging.getLogger(__name__)


class SubmissionService:
    async def judging_snapshots(self, assignments: list[object]) -> dict:
        rows = await self.repository.get_many([a.submission_id for a in assignments])
        return {s.team_id: s for s in rows}

    async def final_for_judging(self, team_ids: list[UUID], round_: object) -> dict:
        rows = await self.repository.finals(team_ids, round_.id)
        return {s.team_id: s for s in rows if utc(s.submitted_at) < utc(round_.submission_deadline)}

    def __init__(
        self,
        repository: SubmissionRepository,
        teams: TeamService,
        events: EventService,
        auth: AuthService,
        judging: JudgingService,
        settings: Settings,
    ) -> None:
        self.repository = repository
        self.teams = teams
        self.events = events
        self.auth = auth
        self.judging = judging
        self.settings = settings

    @staticmethod
    def active(actor: UserOutput, team: object, *, leader: bool = False) -> None:
        if actor.is_admin or not any(
            m.user_id == actor.id and m.status == "active" for m in team.members
        ):
            raise ApiError(403, "FORBIDDEN", "Active team membership is required")
        if leader and team.leader_id != actor.id:
            raise ApiError(403, "NOT_TEAM_LEADER", "Only the active leader may submit")

    async def locked(
        self, actor: UserOutput, team_id: UUID, *, leader: bool = False
    ) -> tuple[object, object, UserOutput]:
        initial = await self.teams.get(team_id)
        actor = await self.auth.lock_actor(actor)
        event = await self.events.get(initial.event_id, lock=True)
        team = await self.teams.get(team_id, lock=True)
        self.active(actor, team, leader=leader)
        return team, event, actor

    async def accepting(
        self, event: object, team: object, round_: object, now: datetime | None = None
    ) -> None:
        now = now or datetime.now(UTC)
        if team.status != "approved":
            raise ApiError(409, "TEAM_NOT_APPROVED", "Team must be approved")
        if event.status != "ongoing" or event.archived_at or now < utc(round_.starts_at):
            raise ApiError(409, "ROUND_NOT_OPEN", "Round is not accepting submissions")
        if now >= utc(round_.submission_deadline):
            raise ApiError(409, "DEADLINE_PASSED", "Submission deadline has passed")
        if not await self.events.submission_eligible(round_, team.id):
            raise ApiError(409, "ROUND_NOT_ELIGIBLE", "Team is not eligible for this round")
        if await self.judging.submissions_frozen(round_.id):
            raise ApiError(409, "SUBMISSIONS_FROZEN", "Judging has started for this round")

    async def presign(self, actor: UserOutput, data: PresignInput) -> PresignOutput:
        team, event, actor = await self.locked(actor, data.team_id)
        storage.validate_metadata(data.filename, data.content_type, data.size)
        rounds = await self.events.rounds(event.id)
        now = datetime.now(UTC)
        round_ = None
        for candidate in rounds:
            if utc(candidate.starts_at) <= now < utc(
                candidate.submission_deadline
            ) and await self.events.submission_eligible(candidate, team.id):
                round_ = candidate
                break
        if round_ is None:
            raise ApiError(409, "ROUND_NOT_OPEN", "No eligible round is accepting uploads")
        await self.accepting(event, team, round_)
        key = f"uploads/{team.id}/{uuid4()}{PurePosixPath(data.filename).suffix.lower()}"
        client = storage.Storage(self.settings)
        url, fields = await run_in_threadpool(client.presign, key, data.content_type, data.size)
        await self.repository.add_upload(
            key=key,
            team_id=team.id,
            uploaded_by=actor.id,
            filename=data.filename,
            size=data.size,
            content_type=data.content_type,
            created_at=now,
        )
        await self.events.log(actor, "upload.presigned", team.id, {"key": key}, "team")
        await self.repository.commit()
        return PresignOutput(upload_url=url, headers={}, fields=fields, file_key=key)

    async def render(
        self, rows: list[Submission], *, downloads: bool = False
    ) -> list[SubmissionOutput]:
        if not rows:
            return []
        versions = await self.repository.latest(list({s.team_id for s in rows}), rows[0].round_id)
        client = (
            storage.Storage(self.settings) if downloads and any(s.files for s in rows) else None
        )
        result = []
        for row in rows:
            files = []
            for file in row.files:
                output = FileOutput.model_validate(file)
                if client:
                    output.download_url = await run_in_threadpool(
                        client.download, file.storage_key, file.filename
                    )
                files.append(output)
            values = {
                k: getattr(row, k)
                for k in SubmissionOutput.model_fields
                if k not in {"files", "is_final"}
            }
            result.append(
                SubmissionOutput(
                    **values, files=files, is_final=versions.get(row.team_id) == row.version
                )
            )
        return result

    async def submit(
        self, actor: UserOutput, team_id: UUID, round_id: UUID, key: str, data: SubmissionInput
    ) -> SubmissionOutput:
        team, event, actor = await self.locked(actor, team_id, leader=True)
        round_ = await self.events.submission_round(event.id, round_id)
        values = data.model_dump(mode="json")
        digest = hashlib.sha256(
            json.dumps(values, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()
        previous = await self.repository.receipt(actor.id, team_id, round_id, key)
        if previous:
            if previous.payload_hash != digest:
                raise ApiError(409, "IDEMPOTENCY_CONFLICT", "Key was used with another payload")
            return (await self.render([previous]))[0]
        await self.accepting(event, team, round_)
        if data.repo_url != team.repo_url:
            raise ApiError(
                422, "REPO_MISMATCH", "Repository must match the approved team repository"
            )
        uploads = await self.repository.uploads(data.file_keys)
        if len(uploads) != len(data.file_keys) or any(
            u.team_id != team.id or u.consumed_at for u in uploads
        ):
            raise ApiError(
                422, "FILE_NOT_UPLOADED", "File keys must be unused uploads owned by this team"
            )
        sha = await github_client.head_sha(data.repo_url, self.settings)
        submission_id = uuid4()
        files = []
        copies = []
        client = storage.Storage(self.settings) if uploads else None
        try:
            for upload in uploads:
                suffix = PurePosixPath(upload.filename).suffix.lower()
                storage_key = f"submissions/{submission_id}/{uuid4()}{suffix}"
                copies.append(storage_key)
                await run_in_threadpool(
                    client.seal,
                    upload.key,
                    storage_key,
                    upload.filename,
                    upload.content_type,
                    upload.size,
                )
                files.append(
                    {
                        "key": upload.key,
                        "storage_key": storage_key,
                        "filename": upload.filename,
                        "size": upload.size,
                        "content_type": upload.content_type,
                    }
                )
            # Provider có thể mất nhiều giây; dùng cùng một mốc cho kiểm tra hạn và biên nhận.
            now = datetime.now(UTC)
            await self.accepting(event, team, round_, now)
        except Exception:
            for copy in copies:
                try:
                    await run_in_threadpool(client.discard_unsubmitted, copy)
                except ApiError:
                    logger.warning("Unsubmitted storage copy requires cleanup")
            raise
        for upload in uploads:
            upload.consumed_at = now
        latest = await self.repository.latest([team_id], round_id)
        row = await self.repository.create(
            {
                "id": submission_id,
                "team_id": team_id,
                "round_id": round_id,
                "submitted_by": actor.id,
                "version": latest.get(team_id, 0) + 1,
                "submitted_at": now,
                "idempotency_key": key,
                "payload_hash": digest,
                "commit_sha": sha,
                **{k: v for k, v in values.items() if k != "file_keys"},
            },
            files,
        )
        await self.events.log(
            actor,
            "submission.created",
            row.id,
            {"team_id": team_id, "round_id": round_id, "version": row.version, "commit_sha": sha},
            "submission",
        )
        output = (await self.render([row]))[0]
        await self.repository.commit()
        return output

    async def authorize_read(self, actor: UserOutput, team_id: UUID, round_id: UUID) -> None:
        team = await self.teams.get(team_id)
        await self.events.submission_round(team.event_id, round_id)
        await self.events.read(team.event_id, actor)
        if actor.is_admin or any(
            m.user_id == actor.id and m.status == "active" for m in team.members
        ):
            return
        roles = {
            r.role for r in await self.auth.roles_in_event(team.event_id) if r.user_id == actor.id
        }
        if "organizer" in roles or (
            roles & {"judge", "mentor"}
            and await self.judging.can_read_submission(actor.id, team_id, round_id)
        ):
            return
        raise ApiError(403, "FORBIDDEN", "Submission is outside the user's scope")

    async def list(
        self, actor: UserOutput, team_id: UUID, round_id: UUID, limit: int, offset: int
    ) -> Page[SubmissionOutput]:
        await self.authorize_read(actor, team_id, round_id)
        rows, total = await self.repository.list([team_id], round_id, limit, offset)
        return Page(items=await self.render(rows), total=total)

    async def get(self, actor: UserOutput, submission_id: UUID) -> SubmissionOutput:
        row = await self.repository.get(submission_id)
        if row is None:
            raise ApiError(404, "SUBMISSION_NOT_FOUND", "Submission not found")
        await self.authorize_read(actor, row.team_id, row.round_id)
        return (await self.render([row], downloads=True))[0]

    async def round_list(
        self, actor: UserOutput, event_id: UUID, round_id: UUID, limit: int, offset: int
    ) -> Page[RoundSubmission]:
        await self.events.get(event_id)
        await self.events.submission_round(event_id, round_id)
        await self.events.require_organizer(actor, event_id, admin_read=True)
        teams = await self.teams.list(actor, event_id, "approved", None, None, limit, offset)
        rows, _ = await self.repository.list(
            [t.id for t in teams.items], round_id, 100, 0, final=True
        )
        outputs = {s.team_id: s for s in await self.render(rows)}
        return Page(
            items=[
                RoundSubmission(team_id=t.id, name=t.name, submission=outputs.get(t.id))
                for t in teams.items
            ],
            total=teams.total,
        )
