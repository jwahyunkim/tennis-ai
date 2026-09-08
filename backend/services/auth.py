import asyncio
import hashlib
import re
import secrets
from datetime import UTC, datetime, timedelta
from uuid import UUID

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError
from sqlalchemy.exc import IntegrityError

from backend.core.errors import AppError
from backend.models.account import AuthSession, User
from backend.repositories.accounts import AccountRepository
from backend.schemas.auth import AuthResponse, UserResponse

_password_hasher = PasswordHasher()
_token_pattern = re.compile(r"[A-Za-z0-9_-]{43}\Z")


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


async def hash_password(password: str) -> str:
    return await asyncio.to_thread(_password_hasher.hash, password)


async def verify_password(password_hash: str, password: str) -> bool:
    try:
        return await asyncio.to_thread(_password_hasher.verify, password_hash, password)
    except (VerificationError, InvalidHashError):
        return False


class AuthService:
    def __init__(
        self,
        repository: AccountRepository,
        *,
        session_hours: int = 24,
        max_attempts: int = 10,
        lockout_seconds: int = 900,
    ) -> None:
        self._repository = repository
        self._session_hours = session_hours
        self._max_attempts = max_attempts
        self._lockout_seconds = lockout_seconds

    async def _reserve_attempts(self, action: str, identity: str, client: str) -> str:
        now = datetime.now(UTC)
        cutoff = now - timedelta(seconds=self._lockout_seconds)
        identity_bucket = hash_token(f"{action}:identity:{identity}")
        client_bucket = hash_token(f"{action}:client:{client}")
        attempts = await self._repository.reserve_attempt(identity_bucket, now, cutoff)
        client_attempts = await self._repository.reserve_attempt(
            client_bucket, now, cutoff
        )
        # Persist attempts before expensive verification, including rejected requests.
        await self._repository.commit()
        if attempts > self._max_attempts or client_attempts > self._max_attempts * 5:
            raise AppError(
                429, "auth_rate_limited", "Too many attempts. Try again later."
            )
        return identity_bucket

    async def _issue_session(self, user: User) -> AuthResponse:
        token = secrets.token_urlsafe(32)
        expires_at = datetime.now(UTC) + timedelta(hours=self._session_hours)
        self._repository.add_session(
            AuthSession(
                token_hash=hash_token(token), user_id=user.id, expires_at=expires_at
            )
        )
        await self._repository.commit()
        return AuthResponse(
            access_token=token,
            expires_at=expires_at,
            user=UserResponse.model_validate(user),
        )

    async def register(
        self, email: str, password: str, display_name: str, client: str
    ) -> AuthResponse:
        await self._reserve_attempts("register", email, client)
        user = User(
            email=email,
            display_name=display_name,
            password_hash=await hash_password(password),
        )
        try:
            await self._repository.add_user(user)
        except IntegrityError:
            await self._repository.rollback()
            raise AppError(
                409, "account_exists", "An account with this email already exists."
            ) from None
        return await self._issue_session(user)

    async def login(self, email: str, password: str, client: str) -> AuthResponse:
        bucket = await self._reserve_attempts("login", email, client)
        # Serialize login with password changes so revoked credentials cannot issue
        # a new session after the password change has completed.
        user = await self._repository.get_by_email(email, lock=True)
        if user is None:
            # Perform the same expensive password work for unknown accounts.
            await hash_password(password)
            await self._repository.rollback()
            raise AppError(
                401, "invalid_credentials", "Email or password is incorrect."
            )
        if not await verify_password(user.password_hash, password):
            await self._repository.rollback()
            raise AppError(
                401, "invalid_credentials", "Email or password is incorrect."
            )
        if _password_hasher.check_needs_rehash(user.password_hash):
            user.password_hash = await hash_password(password)
        await self._repository.reset_attempts(bucket)
        return await self._issue_session(user)

    async def authenticate(self, token: str) -> User:
        if _token_pattern.fullmatch(token) is None:
            raise AppError(401, "unauthorized", "Sign in to continue.")
        user = await self._repository.authenticated_user(
            hash_token(token), datetime.now(UTC)
        )
        if user is None:
            raise AppError(401, "unauthorized", "Sign in to continue.")
        return user

    async def update_profile(self, user_id: UUID, display_name: str) -> User:
        user = await self._repository.lock_user(user_id)
        if user is None:
            raise AppError(401, "unauthorized", "Sign in to continue.")
        user.display_name = display_name
        await self._repository.commit()
        return user

    async def logout(self, token: str) -> None:
        await self._repository.delete_session(hash_token(token))
        await self._repository.commit()

    async def change_password(
        self, user_id: UUID, current_password: str, new_password: str, client: str
    ) -> None:
        bucket = await self._reserve_attempts("password", str(user_id), client)
        user = await self._repository.lock_user(user_id)
        if user is None or not await verify_password(
            user.password_hash, current_password
        ):
            await self._repository.rollback()
            raise AppError(401, "invalid_credentials", "Current password is incorrect.")
        user.password_hash = await hash_password(new_password)
        await self._repository.delete_user_sessions(user_id)
        await self._repository.reset_attempts(bucket)
        await self._repository.commit()
