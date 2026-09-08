"""Declarative base shared by PostgreSQL models."""

from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    """Collect model metadata for Alembic migrations."""
