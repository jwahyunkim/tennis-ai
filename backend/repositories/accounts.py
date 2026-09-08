from datetime import datetime
from uuid import UUID

from sqlalchemy import case, delete, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from backend.models.account import AuthAttempt, AuthSession, User


class AccountRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_by_email(self, email: str, *, lock: bool = False) -> User | None:
        statement = select(User).where(User.email == email)
        if lock:
            statement = statement.with_for_update()
        return await self._session.scalar(statement)

    async def lock_user(self, user_id: UUID) -> User | None:
        return await self._session.scalar(
            select(User)
            .where(User.id == user_id)
            .with_for_update()
            .execution_options(populate_existing=True)
        )

    async def add_user(self, user: User) -> None:
        self._session.add(user)
        await self._session.flush()

    def add_session(self, session: AuthSession) -> None:
        self._session.add(session)

    async def authenticated_user(self, token_hash: str, now: datetime) -> User | None:
        return await self._session.scalar(
            select(User)
            .join(AuthSession, AuthSession.user_id == User.id)
            .where(
                AuthSession.token_hash == token_hash,
                AuthSession.expires_at > now,
            )
        )

    async def delete_session(self, token_hash: str) -> None:
        await self._session.execute(
            delete(AuthSession).where(AuthSession.token_hash == token_hash)
        )

    async def delete_user_sessions(self, user_id: UUID) -> None:
        await self._session.execute(
            delete(AuthSession).where(AuthSession.user_id == user_id)
        )

    async def reserve_attempt(
        self, bucket_hash: str, now: datetime, window_cutoff: datetime
    ) -> int:
        # A PostgreSQL upsert serializes concurrent attempts across API processes.
        expired = AuthAttempt.window_started_at <= window_cutoff
        result = await self._session.scalar(
            insert(AuthAttempt)
            .values(bucket_hash=bucket_hash, attempts=1, window_started_at=now)
            .on_conflict_do_update(
                index_elements=[AuthAttempt.bucket_hash],
                set_={
                    "attempts": case((expired, 1), else_=AuthAttempt.attempts + 1),
                    "window_started_at": case(
                        (expired, now), else_=AuthAttempt.window_started_at
                    ),
                },
            )
            .returning(AuthAttempt.attempts)
        )
        assert result is not None
        return result

    async def reset_attempts(self, bucket_hash: str) -> None:
        await self._session.execute(
            delete(AuthAttempt).where(AuthAttempt.bucket_hash == bucket_hash)
        )

    async def prune_expired(self, now: datetime, attempt_cutoff: datetime) -> None:
        await self._session.execute(
            delete(AuthSession).where(AuthSession.expires_at <= now)
        )
        await self._session.execute(
            delete(AuthAttempt).where(AuthAttempt.window_started_at <= attempt_cutoff)
        )

    async def commit(self) -> None:
        await self._session.commit()

    async def rollback(self) -> None:
        await self._session.rollback()
