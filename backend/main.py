import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import async_sessionmaker

from backend.core.config import Settings
from backend.core.database import create_database_engine
from backend.core.errors import AppError
from backend.core.http import RequestBodyTooLarge, RequestMiddleware
from backend.core.storage import create_storage
from backend.routers.auth import router as auth_router
from backend.routers.health import router as health_router
from backend.routers.videos import router as video_router


def create_app(settings: Settings | None = None) -> FastAPI:
    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        logging.basicConfig(level=logging.INFO, format="%(message)s")
        app.state.settings = settings if settings is not None else Settings()
        engine = create_database_engine(app.state.settings)
        app.state.engine = engine
        app.state.session_factory = async_sessionmaker(engine, expire_on_commit=False)
        try:
            app.state.storage = await create_storage(app.state.settings)
            yield
        finally:
            await engine.dispose()

    app = FastAPI(title="Tennis AI API", lifespan=lifespan)
    # Settings are resolved lazily, so importing the app still needs no credentials.
    # Per-file limits are additionally enforced while copying uploads.
    app.add_middleware(RequestMiddleware, max_body_bytes=1024**3 + 1024**2)

    @app.exception_handler(AppError)
    async def app_error(request, exc: AppError):
        return JSONResponse(
            status_code=exc.status_code,
            content={"error": {"code": exc.code, "message": exc.message}},
        )

    @app.exception_handler(RequestValidationError)
    async def validation_error(request, exc):
        # FastAPI's default includes submitted input, including rejected passwords.
        return JSONResponse(
            status_code=422,
            content={
                "error": {
                    "code": "validation_error",
                    "message": "입력 형식을 확인하세요.",
                }
            },
        )

    @app.exception_handler(RequestBodyTooLarge)
    async def body_too_large(request, exc):
        return JSONResponse(
            status_code=413,
            content={
                "error": {
                    "code": "request_too_large",
                    "message": "요청 용량을 초과했습니다.",
                }
            },
        )

    app.include_router(health_router)
    app.include_router(auth_router)
    app.include_router(video_router)
    return app


app = create_app()
