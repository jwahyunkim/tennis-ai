from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from sqlalchemy.ext.asyncio import async_sessionmaker

from backend.core.config import Settings
from backend.core.database import create_database_engine
from backend.routers.health import router as health_router


def create_app(settings: Settings | None = None) -> FastAPI:
    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        app.state.settings = settings if settings is not None else Settings()
        engine = create_database_engine(app.state.settings)
        app.state.engine = engine
        app.state.session_factory = async_sessionmaker(engine, expire_on_commit=False)
        try:
            yield
        finally:
            await engine.dispose()

    app = FastAPI(title="Tennis AI API", lifespan=lifespan)
    app.include_router(health_router)
    return app


app = create_app()
