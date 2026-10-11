from typing import Annotated

from fastapi import Depends, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

from backend.core.dependencies import get_session
from backend.core.errors import AppError
from backend.models.account import User
from backend.repositories.accounts import AccountRepository
from backend.services.auth import AuthService

_bearer = HTTPBearer(auto_error=False)


async def get_auth_service(
    request: Request,
    session: Annotated[AsyncSession, Depends(get_session)],
) -> AuthService:
    settings = request.app.state.settings
    return AuthService(
        AccountRepository(session),
        session_hours=settings.auth_session_hours,
        max_attempts=settings.auth_max_attempts,
        lockout_seconds=settings.auth_lockout_seconds,
    )


def get_bearer_token(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer)],
) -> str:
    if credentials is None:
        raise AppError(401, "unauthorized", "Sign in to continue.")
    return credentials.credentials


async def get_current_user(
    token: Annotated[str, Depends(get_bearer_token)],
    service: Annotated[AuthService, Depends(get_auth_service)],
) -> User:
    return await service.authenticate(token)


def get_client_address(request: Request) -> str:
    # Uvicorn must trust forwarded addresses only from an explicitly trusted proxy.
    return request.client.host if request.client else "unknown"
