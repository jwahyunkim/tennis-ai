from typing import Annotated

from fastapi import APIRouter, Depends, Response, status

from backend.core.auth import (
    get_auth_service,
    get_bearer_token,
    get_client_address,
    get_current_user,
)
from backend.models.account import User
from backend.schemas.auth import (
    AuthResponse,
    LoginRequest,
    PasswordChange,
    ProfileUpdate,
    RegisterRequest,
    UserResponse,
)
from backend.services.auth import AuthService

router = APIRouter(prefix="/api/v1/auth", tags=["auth"])
Service = Annotated[AuthService, Depends(get_auth_service)]
CurrentUser = Annotated[User, Depends(get_current_user)]
ClientAddress = Annotated[str, Depends(get_client_address)]


@router.post(
    "/register", response_model=AuthResponse, status_code=status.HTTP_201_CREATED
)
async def register(
    body: RegisterRequest, service: Service, client: ClientAddress
) -> AuthResponse:
    return await service.register(
        body.email, body.password.get_secret_value(), body.display_name, client
    )


@router.post("/login", response_model=AuthResponse)
async def login(
    body: LoginRequest, service: Service, client: ClientAddress
) -> AuthResponse:
    return await service.login(body.email, body.password.get_secret_value(), client)


@router.get("/me", response_model=UserResponse)
async def profile(user: CurrentUser) -> User:
    return user


@router.patch("/me", response_model=UserResponse)
async def update_profile(
    body: ProfileUpdate, user: CurrentUser, service: Service
) -> User:
    return await service.update_profile(user.id, body.display_name)


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(
    user: CurrentUser,
    token: Annotated[str, Depends(get_bearer_token)],
    service: Service,
) -> Response:
    await service.logout(token)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/password", status_code=status.HTTP_204_NO_CONTENT)
async def change_password(
    body: PasswordChange, user: CurrentUser, service: Service, client: ClientAddress
) -> Response:
    await service.change_password(
        user.id,
        body.current_password.get_secret_value(),
        body.new_password.get_secret_value(),
        client,
    )
    return Response(status_code=status.HTTP_204_NO_CONTENT)
