import asyncio
from unittest.mock import AsyncMock

import pytest
from asyncpg import PostgresError
from sqlalchemy.exc import OperationalError
from sqlalchemy.ext.asyncio import AsyncSession

from backend.repositories.health import HealthRepository


@pytest.mark.parametrize(
    "error",
    [
        ConnectionRefusedError("connection refused"),
        TimeoutError("connection timed out"),
        PostgresError("database unavailable"),
        OperationalError("SELECT 1", {}, Exception("database unavailable")),
    ],
)
async def test_repository_maps_expected_database_failures_to_unavailable(error):
    session = AsyncMock(spec=AsyncSession)
    session.scalar.side_effect = error

    assert await HealthRepository(session).is_available() is False


async def test_repository_does_not_hide_programming_errors():
    session = AsyncMock(spec=AsyncSession)
    session.scalar.side_effect = RuntimeError("unexpected implementation bug")

    with pytest.raises(RuntimeError, match="unexpected implementation bug"):
        await HealthRepository(session).is_available()


async def test_repository_preserves_request_cancellation():
    session = AsyncMock(spec=AsyncSession)
    session.scalar.side_effect = asyncio.CancelledError()

    with pytest.raises(asyncio.CancelledError):
        await HealthRepository(session).is_available()
