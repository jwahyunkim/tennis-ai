from asyncpg import PostgresError
from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession


class HealthRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def is_available(self) -> bool:
        try:
            return await self._session.scalar(select(1)) == 1
        except (SQLAlchemyError, PostgresError, OSError, TimeoutError):
            # Connection errors can contain credentials; expose only availability.
            return False
