from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, Mock
from uuid import uuid4

import pytest
from pydantic import ValidationError

from backend.core.errors import AppError
from backend.models.account import User
from backend.repositories.accounts import AccountRepository
from backend.schemas.auth import LoginRequest, ProfileUpdate, RegisterRequest
from backend.services.auth import (
    AuthService,
    hash_password,
    hash_token,
    verify_password,
)


@pytest.fixture
def account_repository():
    repository = Mock(spec=AccountRepository)
    repository.reserve_attempt.return_value = 1
    return repository


def test_registration_normalizes_email_and_keeps_password_secret():
    body = RegisterRequest(
        email="PLAYER@Example.COM",
        display_name="  Player  ",
        password="tennis-private-password",
    )
    assert body.email == "player@example.com"
    assert body.display_name == "Player"
    assert "tennis-private-password" not in repr(body)
    assert "tennis-private-password" not in body.model_dump_json()


@pytest.mark.parametrize("password", ["short", "x" * 129, 123, None])
def test_invalid_passwords_are_rejected_without_displaying_input(password):
    with pytest.raises(ValidationError) as error:
        LoginRequest(email="player@example.com", password=password)
    assert "input_value" not in str(error.value)


@pytest.mark.parametrize("email", ["bad-address", "a@", "a @example.com"])
def test_invalid_email_is_rejected(email):
    with pytest.raises(ValidationError):
        LoginRequest(email=email, password="long-enough-password")


@pytest.mark.parametrize("display_name", ["", "   ", "x" * 81])
def test_invalid_display_name_is_rejected(display_name):
    with pytest.raises(ValidationError):
        ProfileUpdate(display_name=display_name)


async def test_argon2_password_hash_is_salted_and_verifiable():
    password = "tennis-password-for-tests"
    first = await hash_password(password)
    second = await hash_password(password)
    assert first != second
    assert first.startswith("$argon2id$")
    assert await verify_password(first, password)
    assert not await verify_password(first, "incorrect-password")
    assert not await verify_password("not-an-argon-hash", password)


async def test_rate_limit_persists_attempt_before_rejecting(account_repository):
    account_repository.reserve_attempt.side_effect = [11, 1]
    service = AuthService(account_repository)
    with pytest.raises(AppError) as error:
        await service.login("player@example.com", "password-for-tests", "127.0.0.1")
    assert error.value.status_code == 429
    account_repository.commit.assert_awaited_once()
    account_repository.get_by_email.assert_not_awaited()


async def test_client_rate_limit_applies_across_account_names(account_repository):
    account_repository.reserve_attempt.side_effect = [1, 51]
    service = AuthService(account_repository)
    with pytest.raises(AppError) as error:
        await service.register(
            "new@example.com", "password-for-tests", "Player", "127.0.0.1"
        )
    assert error.value.status_code == 429
    account_repository.commit.assert_awaited_once()
    account_repository.add_user.assert_not_awaited()


async def test_unknown_account_has_same_error_and_expensive_work(
    account_repository, monkeypatch
):
    account_repository.get_by_email.return_value = None
    hasher = AsyncMock(return_value="discarded-hash")
    monkeypatch.setattr("backend.services.auth.hash_password", hasher)
    service = AuthService(account_repository)
    with pytest.raises(AppError) as error:
        await service.login("unknown@example.com", "password-for-tests", "127.0.0.1")
    assert error.value.status_code == 401
    assert error.value.code == "invalid_credentials"
    hasher.assert_awaited_once_with("password-for-tests")
    account_repository.rollback.assert_awaited_once()
    account_repository.add_session.assert_not_called()


async def test_wrong_password_releases_lock_without_resetting_attempts(
    account_repository, monkeypatch
):
    account_repository.get_by_email.return_value = User(
        id=uuid4(),
        email="player@example.com",
        display_name="Player",
        password_hash="stored-hash",
    )
    monkeypatch.setattr(
        "backend.services.auth.verify_password", AsyncMock(return_value=False)
    )
    service = AuthService(account_repository)
    with pytest.raises(AppError) as error:
        await service.login("player@example.com", "incorrect-password", "127.0.0.1")
    assert error.value.status_code == 401
    assert error.value.code == "invalid_credentials"
    account_repository.get_by_email.assert_awaited_once_with(
        "player@example.com", lock=True
    )
    account_repository.rollback.assert_awaited_once()
    account_repository.reset_attempts.assert_not_awaited()
    account_repository.add_session.assert_not_called()


@pytest.mark.parametrize("token", ["", "short", "x" * 44, "!" * 43, "x" * 42 + "\n"])
async def test_malformed_token_does_not_query_database(account_repository, token):
    service = AuthService(account_repository)
    with pytest.raises(AppError) as error:
        await service.authenticate(token)
    assert error.value.status_code == 401
    account_repository.authenticated_user.assert_not_awaited()


async def test_valid_token_is_hashed_before_database_lookup(account_repository):
    token = "a" * 43
    user = User(id=uuid4(), email="player@example.com", display_name="Player")
    account_repository.authenticated_user.return_value = user
    service = AuthService(account_repository)
    assert await service.authenticate(token) is user
    passed_hash, passed_now = account_repository.authenticated_user.await_args.args
    assert passed_hash == hash_token(token)
    assert passed_hash != token
    assert datetime.now(UTC) - passed_now < timedelta(seconds=1)


async def test_profile_update_uses_locked_persisted_user(account_repository):
    user = User(id=uuid4(), email="player@example.com", display_name="Before")
    account_repository.lock_user.return_value = user
    service = AuthService(account_repository)
    updated = await service.update_profile(user.id, "After")
    assert updated.display_name == "After"
    account_repository.lock_user.assert_awaited_once_with(user.id)
    account_repository.commit.assert_awaited_once()
