from pathlib import Path
from typing import Literal

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy import URL


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=Path(__file__).resolve().parents[2] / "infra" / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
        frozen=True,
        hide_input_in_errors=True,
    )

    postgres_host: str = Field(default="127.0.0.1", min_length=1)
    postgres_port: int = Field(default=5432, ge=1, le=65535)
    postgres_db: str = Field(default="tennis_ai", min_length=1)
    postgres_user: str = Field(default="tennis_ai", min_length=1)
    postgres_password: SecretStr = Field(min_length=1)
    database_timeout_seconds: float = Field(default=5, gt=0, le=60)
    auth_session_hours: int = Field(default=24, ge=1, le=720)
    auth_max_attempts: int = Field(default=10, ge=1, le=100)
    auth_lockout_seconds: int = Field(default=900, ge=1, le=86400)
    storage_backend: Literal["local", "s3"] = "local"
    storage_local_path: Path = Field(
        default_factory=lambda: Path.home() / ".local/share/tennis-ai/media"
    )
    s3_bucket: str = ""
    s3_endpoint_url: str | None = None
    s3_region: str = "us-east-1"
    max_upload_bytes: int = Field(default=250 * 1024 * 1024, ge=1024, le=1024**3)
    max_user_storage_bytes: int = Field(default=2 * 1024**3, ge=1024)
    max_video_seconds: float = Field(default=120, gt=0, le=600)
    worker_poll_seconds: float = Field(default=2, gt=0, le=30)
    worker_lease_seconds: int = Field(default=120, ge=100, le=3600)
    worker_max_attempts: int = Field(default=3, ge=1, le=10)
    worker_heartbeat_path: Path = Path("/tmp/tennis-ai-worker-heartbeat")

    @property
    def database_url(self) -> URL:
        return URL.create(
            "postgresql+asyncpg",
            username=self.postgres_user,
            password=self.postgres_password.get_secret_value(),
            host=self.postgres_host,
            port=self.postgres_port,
            database=self.postgres_db,
        )
