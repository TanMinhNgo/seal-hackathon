from datetime import datetime
from uuid import UUID

from pydantic import Field, HttpUrl, field_validator

from app.core.schemas import Output
from app.modules.auth.schemas import Input


class PresignInput(Input):
    team_id: UUID
    filename: str = Field(min_length=1, max_length=255)
    content_type: str = Field(min_length=1, max_length=100)
    size: int = Field(strict=True, gt=0)

    @field_validator("filename")
    @classmethod
    def safe_filename(cls, value: str) -> str:
        if any(c in value for c in ("/", "\\")) or any(ord(c) < 32 or ord(c) == 127 for c in value):
            raise ValueError("Filename must not contain paths or control characters")
        return value


class PresignOutput(Output):
    upload_url: str
    method: str = "POST"
    headers: dict[str, str]
    fields: dict[str, str]
    file_key: str


class SubmissionInput(Input):
    repo_url: str = Field(min_length=1, max_length=2048)
    demo_url: HttpUrl | None = Field(default=None, max_length=2048)
    video_url: HttpUrl | None = Field(default=None, max_length=2048)
    description: str | None = Field(default=None, max_length=20000)
    file_keys: list[str] = Field(default_factory=list, max_length=10)

    @field_validator("file_keys")
    @classmethod
    def unique_keys(cls, value: list[str]) -> list[str]:
        if len(set(value)) != len(value) or any(not 1 <= len(k) <= 255 for k in value):
            raise ValueError("File keys must be unique and at most 255 characters")
        return value


class FileOutput(Output):
    key: str
    filename: str
    size: int
    content_type: str
    download_url: str | None = None


class SubmissionOutput(Output):
    id: UUID
    team_id: UUID
    round_id: UUID
    version: int
    repo_url: str
    commit_sha: str
    demo_url: str | None
    video_url: str | None
    description: str | None
    files: list[FileOutput]
    submitted_by: UUID
    submitted_at: datetime
    is_final: bool


class RoundSubmission(Output):
    team_id: UUID
    name: str
    submission: SubmissionOutput | None
