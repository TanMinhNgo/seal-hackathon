from typing import Literal

from app.core.schemas import Output

ReportType = Literal["teams", "submissions", "leaderboard"]
ReportFormat = Literal["xlsx", "pdf"]


class Dashboard(Output):
    registrations: int
    teams_by_status: dict[str, int]
    submissions_by_round: dict[str, int]
    judging_progress: dict[str, int]
    commits_per_day: dict[str, int]
    ai_verdict_counts: dict[str, int]
    unassigned_teams: int
    unsubmitted_teams: int
    unresolved_questions: int
    mentor_progress: dict[str, int]
    sync_errors: int
    ai_job_counts: dict[str, int]
