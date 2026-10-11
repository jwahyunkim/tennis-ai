from datetime import datetime
from typing import Annotated, Literal
from uuid import UUID

from pydantic import (
    BaseModel,
    ConfigDict,
    EmailStr,
    Field,
    SecretStr,
    StringConstraints,
    field_validator,
)

Password = Annotated[SecretStr, Field(min_length=10, max_length=128)]
DisplayName = Annotated[
    str, StringConstraints(strip_whitespace=True, min_length=1, max_length=80)
]


class AuthInput(BaseModel):
    model_config = ConfigDict(extra="forbid", hide_input_in_errors=True)


class LoginRequest(AuthInput):
    email: EmailStr = Field(max_length=254)
    password: Password

    @field_validator("email")
    @classmethod
    def normalize_email(cls, value: str) -> str:
        return value.lower()


class RegisterRequest(LoginRequest):
    display_name: DisplayName


class ProfileUpdate(AuthInput):
    display_name: DisplayName


class PasswordChange(AuthInput):
    current_password: Password
    new_password: Password


class UserResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    email: str
    display_name: str
    created_at: datetime


class AuthResponse(BaseModel):
    access_token: str
    token_type: Literal["bearer"] = "bearer"
    expires_at: datetime
    user: UserResponse
