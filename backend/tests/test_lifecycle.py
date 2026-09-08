import pytest
from sqlalchemy.ext.asyncio import AsyncEngine
from starlette.requests import Request

from backend.core.dependencies import get_session
from backend.main import create_app


@pytest.mark.parametrize("request_fails", [False, True])
async def test_lifespan_disposes_engine(settings, monkeypatch, request_fails):
    app = create_app(settings)
    disposed = []
    original_dispose = AsyncEngine.dispose

    async def dispose(engine, *args, **kwargs):
        disposed.append(engine)
        await original_dispose(engine, *args, **kwargs)

    monkeypatch.setattr(AsyncEngine, "dispose", dispose)

    async def run_lifespan():
        async with app.router.lifespan_context(app):
            assert app.state.settings is settings
            if request_fails:
                raise RuntimeError("application failed")

    if request_fails:
        with pytest.raises(RuntimeError, match="application failed"):
            await run_lifespan()
    else:
        await run_lifespan()

    assert disposed == [app.state.engine]


@pytest.mark.parametrize("request_fails", [False, True])
async def test_session_dependency_closes_uncommitted_transaction(
    settings, request_fails
):
    app = create_app(settings)

    async with app.router.lifespan_context(app):
        request = Request({"type": "http", "app": app})
        dependency = get_session(request)
        session = await anext(dependency)
        # Starting the ORM transaction is lazy and does not connect to PostgreSQL.
        await session.begin()
        assert session.in_transaction()

        if request_fails:
            with pytest.raises(RuntimeError, match="request failed"):
                await dependency.athrow(RuntimeError("request failed"))
        else:
            with pytest.raises(StopAsyncIteration):
                await anext(dependency)

        assert not session.in_transaction()
