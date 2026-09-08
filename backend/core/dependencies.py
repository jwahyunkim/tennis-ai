from collections.abc import AsyncIterator
from typing import Annotated

from fastapi import Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from backend.repositories.health import HealthRepository
from backend.services.health import HealthService


async def get_session(request: Request) -> AsyncIterator[AsyncSession]:
    # Closing the session rolls back unfinished work; services own commits.
    async with request.app.state.session_factory() as session:
        yield session


async def get_health_service(
    request: Request,
    session: Annotated[AsyncSession, Depends(get_session)],
) -> HealthService:
    return HealthService(
        HealthRepository(session),
        timeout_seconds=request.app.state.settings.database_timeout_seconds,
    )
