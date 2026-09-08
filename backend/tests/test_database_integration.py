import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select
from starlette.requests import Request

from backend.core.dependencies import get_session
from backend.main import create_app


@pytest.mark.integration
async def test_readiness_with_real_postgresql():
    app = create_app()

    async with app.router.lifespan_context(app):
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            response = await client.get("/health/ready")

    assert response.status_code == 200
    assert response.json() == {"status": "ok", "database": "ok"}


@pytest.mark.integration
async def test_request_cleanup_ends_real_database_transaction():
    app = create_app()

    async with app.router.lifespan_context(app):
        dependency = get_session(Request({"type": "http", "app": app}))
        session = await anext(dependency)
        assert await session.scalar(select(1)) == 1
        assert session.in_transaction()

        await dependency.aclose()

        assert not session.in_transaction()
