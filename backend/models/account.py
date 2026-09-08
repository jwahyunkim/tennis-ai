from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column

from backend.models.base import Base


class User(Base):
    __tablename__ = "users"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    email: Mapped[str] = mapped_column(String(254), unique=True)
    display_name: Mapped[str] = mapped_column(String(80))
    password_hash: Mapped[str] = mapped_column(String(255))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class AuthSession(Base):
    __tablename__ = "auth_sessions"

    token_hash: Mapped[str] = mapped_column(String(64), primary_key=True)
    user_id: Mapped[UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)


class AuthAttempt(Base):
    __tablename__ = "auth_attempts"
    __table_args__ = (CheckConstraint("attempts >= 1", name="positive_auth_attempts"),)

    # Hash both email and client address buckets; do not persist raw addresses.
    bucket_hash: Mapped[str] = mapped_column(String(64), primary_key=True)
    attempts: Mapped[int] = mapped_column(Integer)
    window_started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), index=True
    )
