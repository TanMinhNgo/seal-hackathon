import logging
from datetime import UTC, datetime, timedelta

from app.core.config import Settings
from app.core.schemas import utc
from app.integrations import mailer, storage
from app.modules.auth.service import AuthService
from app.modules.events.service import EventService
from app.modules.submissions.repository import SubmissionJobRepository
from app.modules.teams.service import TeamService

logger = logging.getLogger(__name__)


class SubmissionJobs:
    def __init__(self, repository: SubmissionJobRepository, settings: Settings) -> None:
        self.repository = repository
        self.settings = settings

    def remind(self) -> int:
        if not self.settings.smtp_host:
            return 0
        now = datetime.now(UTC)
        count = 0
        session = self.repository.session
        for round_, eligible in EventService.reminder_rounds(session, now):
            remaining = utc(round_.submission_deadline) - now
            if remaining > timedelta(hours=24):
                continue
            hours = 1 if remaining <= timedelta(hours=1) else 24
            teams = TeamService.reminder_teams(session, round_.event_id, eligible)
            users = AuthService.reminder_users(session, [t.leader_id for t in teams])
            for team in teams:
                leader = users.get(team.leader_id)
                if leader is None:
                    continue
                claim = self.repository.claim(team.id, round_.id, hours, now)
                if claim is None:
                    continue
                try:
                    mailer.send_email(
                        str(leader.email),
                        f"SEAL - Submission deadline ({hours}h)",
                        f"Team {team.name}, {round_.name}: "
                        f"deadline {utc(round_.submission_deadline).isoformat()}. "
                        "A successful upload is not a submission receipt.",
                    )
                except Exception:
                    self.repository.finish(claim, "failed")
                    logger.warning(
                        "Submission reminder failed; receipt requires manual review",
                        extra={"reminder_id": str(claim.id)},
                    )
                else:
                    self.repository.finish(claim, "accepted")
                    count += 1
        return count

    def cleanup(self) -> int:
        client = storage.Storage(self.settings)
        before = datetime.now(UTC) - timedelta(hours=24)
        total = 0
        while count := self.repository.cleanup(before, client):
            total += count
        return total
