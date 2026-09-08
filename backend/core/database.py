from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine

from backend.core.config import Settings


def create_database_engine(settings: Settings) -> AsyncEngine:
    return create_async_engine(
        settings.database_url,
        pool_pre_ping=True,
        pool_timeout=settings.database_timeout_seconds,
        connect_args={
            "timeout": settings.database_timeout_seconds,
            "command_timeout": settings.database_timeout_seconds,
        },
    )
