from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict


class JobResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True, frozen=True)

    id: UUID
    status: Literal[
        "queued", "processing", "awaiting_model", "succeeded", "failed", "cancelled"
    ]
    attempts: int
    error_code: str | None
    created_at: datetime
    updated_at: datetime


class ModelResponse(BaseModel):
    model_config = ConfigDict(frozen=True)

    id: UUID
    format: Literal["glb"]
    model_version: str
    created_at: datetime
    download_path: str


class VideoResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True, frozen=True)

    id: UUID
    filename: str
    content_type: str
    size_bytes: int
    created_at: datetime
    duration_seconds: float | None
    width: int | None
    height: int | None
    status: Literal["uploading", "uploaded", "ready", "failed"]
    job: JobResponse | None = None
    model: ModelResponse | None = None


class VideoPage(BaseModel):
    items: list[VideoResponse]
    total: int
    limit: int
    offset: int
