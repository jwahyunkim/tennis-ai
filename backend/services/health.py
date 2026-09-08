import asyncio
from typing import Protocol


class DatabaseProbe(Protocol):
    async def is_available(self) -> bool: ...


class HealthService:
    def __init__(self, repository: DatabaseProbe, timeout_seconds: float = 5) -> None:
        self._repository = repository
        self._timeout_seconds = timeout_seconds

    async def is_ready(self) -> bool:
        try:
            async with asyncio.timeout(self._timeout_seconds):
                return await self._repository.is_available()
        except TimeoutError:
            return False
