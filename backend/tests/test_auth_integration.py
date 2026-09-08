import asyncio
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from sqlalchemy import select, update

from backend.models.account import AuthAttempt, AuthSession, User
from backend.services.auth import hash_token

pytestmark = pytest.mark.integration
PASSWORD = "integration-tennis-password"


async def register(client, *, email=None):
    email = email or f"player-{uuid4().hex}@example.com"
    response = await client.post(
        "/api/v1/auth/register",
        json={"email": email, "password": PASSWORD, "display_name": "Test Player"},
    )
    assert response.status_code == 201, response.text
    return response.json()


def bearer(auth):
    return {"Authorization": f"Bearer {auth['access_token']}"}


async def test_register_login_profile_logout_and_password_change(api_client):
    account = await register(api_client)
    headers = bearer(account)
    assert account["token_type"] == "bearer"
    assert "password" not in account["user"]
    assert "password_hash" not in account["user"]

    response = await api_client.get("/api/v1/auth/me", headers=headers)
    assert response.status_code == 200
    assert response.json()["id"] == account["user"]["id"]

    response = await api_client.patch(
        "/api/v1/auth/me", headers=headers, json={"display_name": "Updated Player"}
    )
    assert response.status_code == 200
    assert response.json()["display_name"] == "Updated Player"

    response = await api_client.post(
        "/api/v1/auth/login",
        json={"email": account["user"]["email"].upper(), "password": PASSWORD},
    )
    assert response.status_code == 200
    assert response.headers["Cache-Control"] == "no-store"
    second_headers = bearer(response.json())

    response = await api_client.post(
        "/api/v1/auth/password",
        headers=headers,
        json={"current_password": PASSWORD, "new_password": "new-test-tennis-password"},
    )
    assert response.status_code == 204
    for session_headers in (headers, second_headers):
        response = await api_client.get("/api/v1/auth/me", headers=session_headers)
        assert response.status_code == 401

    response = await api_client.post(
        "/api/v1/auth/login",
        json={"email": account["user"]["email"], "password": PASSWORD},
    )
    assert response.status_code == 401
    response = await api_client.post(
        "/api/v1/auth/login",
        json={
            "email": account["user"]["email"],
            "password": "new-test-tennis-password",
        },
    )
    assert response.status_code == 200
    new_headers = bearer(response.json())
    response = await api_client.post("/api/v1/auth/logout", headers=new_headers)
    assert response.status_code == 204
    response = await api_client.get("/api/v1/auth/me", headers=new_headers)
    assert response.status_code == 401


async def test_auth_validation_does_not_echo_password(api_client):
    response = await api_client.post(
        "/api/v1/auth/register",
        json={"email": "bad", "password": "secret", "display_name": "Test"},
    )
    assert response.status_code == 422
    assert "secret" not in response.text
    assert "input" not in response.text


async def test_duplicate_email_is_case_insensitive(api_client):
    account = await register(api_client)
    response = await api_client.post(
        "/api/v1/auth/register",
        json={
            "email": account["user"]["email"].upper(),
            "password": PASSWORD,
            "display_name": "Duplicate",
        },
    )
    assert response.status_code == 409


async def test_missing_and_malformed_authentication_are_rejected(api_client):
    response = await api_client.get("/api/v1/auth/me")
    assert response.status_code == 401
    response = await api_client.get(
        "/api/v1/auth/me", headers={"Authorization": "Bearer invalid-token"}
    )
    assert response.status_code == 401


async def test_concurrent_login_failures_share_persistent_limit(
    api_client, integration_settings
):
    # Unknown account still consumes the database-backed identity bucket.
    email = f"unknown-{uuid4().hex}@example.com"
    responses = await asyncio.gather(
        *(
            api_client.post(
                "/api/v1/auth/login", json={"email": email, "password": PASSWORD}
            )
            for _ in range(integration_settings.auth_max_attempts + 2)
        )
    )
    statuses = [response.status_code for response in responses]
    assert statuses.count(401) == integration_settings.auth_max_attempts
    assert statuses.count(429) == 2


async def test_session_storage_uses_hash_and_enforces_expiry(api_client, api_app):
    account = await register(api_client)
    token = account["access_token"]
    async with api_app.state.session_factory() as session:
        stored = await session.scalar(
            select(AuthSession).where(AuthSession.token_hash == hash_token(token))
        )
        assert stored is not None
        assert stored.token_hash != token
        user = await session.scalar(select(User).where(User.id == stored.user_id))
        assert user.password_hash.startswith("$argon2id$")
        assert user.password_hash != PASSWORD
        await session.execute(
            update(AuthSession)
            .where(AuthSession.token_hash == hash_token(token))
            .values(expires_at=datetime.now(UTC) - timedelta(seconds=1))
        )
        await session.commit()
    response = await api_client.get("/api/v1/auth/me", headers=bearer(account))
    assert response.status_code == 401


async def test_login_lockout_window_expires(api_client, api_app, integration_settings):
    email = f"unknown-{uuid4().hex}@example.com"
    bucket = hash_token(f"login:identity:{email}")
    async with api_app.state.session_factory() as session:
        session.add(
            AuthAttempt(
                bucket_hash=bucket,
                attempts=integration_settings.auth_max_attempts + 1,
                window_started_at=datetime.now(UTC)
                - timedelta(seconds=integration_settings.auth_lockout_seconds + 1),
            )
        )
        await session.commit()
    response = await api_client.post(
        "/api/v1/auth/login", json={"email": email, "password": PASSWORD}
    )
    assert response.status_code == 401
