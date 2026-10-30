from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import AnyHttpUrl, EmailStr, Field, PostgresDsn, RedisDsn, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=Path(__file__).resolve().parents[2] / ".env", extra="ignore"
    )

    app_name: str = "SEAL API"
    database_url: PostgresDsn = "postgresql+asyncpg://seal:seal_dev@127.0.0.1:5434/seal"
    redis_url: RedisDsn = "redis://127.0.0.1:6379/0"
    jwt_secret: SecretStr | None = None
    frontend_url: AnyHttpUrl = "http://localhost:3000"
    cors_origins: list[str] = ["http://localhost:3000"]
    smtp_host: str = ""
    smtp_port: int = Field(default=587, ge=1, le=65535)
    smtp_username: str = ""
    smtp_password: SecretStr | None = None
    smtp_tls: Literal["none", "starttls", "ssl"] = "starttls"
    smtp_from: EmailStr = "noreply@seal.example"
    github_token: SecretStr | None = None
    cloudinary_cloud_name: str = Field(default="", pattern=r"^[A-Za-z0-9_-]*$")
    cloudinary_api_key: SecretStr | None = None
    cloudinary_api_secret: SecretStr | None = None


@lru_cache
def get_settings() -> Settings:
    return Settings()
