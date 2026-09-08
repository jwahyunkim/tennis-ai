from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import BigInteger, CheckConstraint, DateTime, ForeignKey, String, func
from sqlalchemy.orm import Mapped, mapped_column

from backend.models.base import Base


class Video(Base):
    __tablename__ = "videos"
    __table_args__ = (
        CheckConstraint("size_bytes >= 0", name="ck_video_size"),
        CheckConstraint(
            "status IN ('uploading','uploaded','ready','failed')",
            name="ck_video_status",
        ),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    user_id: Mapped[UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    filename: Mapped[str] = mapped_column(String(255))
    content_type: Mapped[str] = mapped_column(String(100))
    storage_key: Mapped[str] = mapped_column(String(200), unique=True)
    size_bytes: Mapped[int] = mapped_column(BigInteger)
    status: Mapped[str] = mapped_column(String(20), default="uploading")
    duration_seconds: Mapped[float | None]
    width: Mapped[int | None]
    height: Mapped[int | None]
    sha256: Mapped[str | None] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), index=True
    )
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class ProcessingJob(Base):
    __tablename__ = "processing_jobs"
    __table_args__ = (
        CheckConstraint(
            "status IN ('queued','processing','awaiting_model','succeeded',"
            "'failed','cancelled')",
            name="ck_job_status",
        ),
        CheckConstraint("attempts >= 0", name="ck_job_attempts"),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    video_id: Mapped[UUID] = mapped_column(
        ForeignKey("videos.id", ondelete="CASCADE"), unique=True
    )
    status: Mapped[str] = mapped_column(String(30), default="queued", index=True)
    attempts: Mapped[int] = mapped_column(default=0)
    error_code: Mapped[str | None] = mapped_column(String(80))
    claim_token: Mapped[UUID | None]
    lease_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    available_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class BodyModel(Base):
    """A genuine reconstruction artifact, populated by a future model adapter."""

    __tablename__ = "body_models"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    video_id: Mapped[UUID] = mapped_column(
        ForeignKey("videos.id", ondelete="CASCADE"), unique=True
    )
    storage_key: Mapped[str] = mapped_column(String(200), unique=True)
    model_version: Mapped[str] = mapped_column(String(100))
    format: Mapped[str] = mapped_column(String(10), default="glb")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class ArtifactUpload(Base):
    """Durable reservation for an object not yet published as a model result."""

    __tablename__ = "artifact_uploads"

    id: Mapped[UUID] = mapped_column(primary_key=True)
    video_id: Mapped[UUID] = mapped_column(
        ForeignKey("videos.id", ondelete="CASCADE"), index=True
    )
    storage_key: Mapped[str] = mapped_column(String(200), unique=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
