import asyncio
from unittest.mock import AsyncMock

import pytest
from httpx import ASGITransport, AsyncClient

from backend.core.dependencies import get_health_service
from backend.main import create_app
from backend.services.health import HealthService


async def test_liveness_does_not_require_a_database(settings):
    app = create_app(settings)

    def unavailable_service():
        raise AssertionError("Liveness must not resolve the database health service")

    app.dependency_overrides[get_health_service] = unavailable_service
    async with app.router.lifespan_context(app):
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            response = await client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


@pytest.mark.parametrize(
    ("ready", "status_code", "payload"),
    [
        (True, 200, {"status": "ok", "database": "ok"}),
        (False, 503, {"status": "unavailable", "database": "unavailable"}),
    ],
)
async def test_readiness_reports_database_availability(
    settings, ready, status_code, payload
):
    app = create_app(settings)
    service = AsyncMock(spec=HealthService)
    service.is_ready.return_value = ready
    app.dependency_overrides[get_health_service] = lambda: service

    async with app.router.lifespan_context(app):
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            response = await client.get("/health/ready")

    assert response.status_code == status_code
    assert response.json() == payload
    service.is_ready.assert_awaited_once()


def test_openapi_documents_readiness_failure(settings):
    app = create_app(settings)

    responses = app.openapi()["paths"]["/health/ready"]["get"]["responses"]

    assert "200" in responses
    assert "503" in responses
    assert "application/json" in responses["503"]["content"]


@pytest.mark.parametrize("available", [True, False])
async def test_health_service_uses_repository_result(available):
    repository = AsyncMock()
    repository.is_available.return_value = available

    assert await HealthService(repository).is_ready() is available
    repository.is_available.assert_awaited_once()


async def test_health_service_bounds_database_check_time():
    cancelled = asyncio.Event()

    class SlowRepository:
        async def is_available(self):
            try:
                await asyncio.Event().wait()
            finally:
                cancelled.set()

    service = HealthService(SlowRepository(), timeout_seconds=0.01)

    assert await asyncio.wait_for(service.is_ready(), timeout=1) is False
    assert cancelled.is_set()


async def test_health_service_does_not_hide_programming_errors():
    repository = AsyncMock()
    repository.is_available.side_effect = RuntimeError("unexpected implementation bug")

    with pytest.raises(RuntimeError, match="unexpected implementation bug"):
        await HealthService(repository).is_ready()
