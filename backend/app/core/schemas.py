from datetime import UTC, datetime

from pydantic import BaseModel, ConfigDict, field_validator


class Page[T](BaseModel):
    items: list[T]
    total: int


class Output(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    @field_validator("*", mode="before")
    @classmethod
    def utc_datetimes(cls, value: object) -> object:
        return utc(value) if isinstance(value, datetime) else value


def utc(value: datetime) -> datetime:
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)
