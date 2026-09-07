#!/usr/bin/env bash

set -euo pipefail

readonly PROJECT_ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../.." && pwd)"
# shellcheck source=.devcontainer/scripts/dev-env.sh
source "${PROJECT_ROOT}/.devcontainer/scripts/dev-env.sh"
cd "${PROJECT_ROOT}"

flutter analyze
flutter test
backend/.venv/bin/python -m pip check

# Exercise the installed HTTP stack and a real async PostgreSQL connection.
# The temporary app below is only an environment probe, not a backend API.
backend/.venv/bin/python - <<'PY'
import asyncio
from pathlib import Path

from dotenv import dotenv_values
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy import URL, select
from sqlalchemy.ext.asyncio import create_async_engine


async def main():
    app = FastAPI()

    @app.get("/health")
    async def health():
        return {"status": "ok"}

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/health")
        assert response.status_code == 200
        assert response.json() == {"status": "ok"}
    print("FastAPI HTTP smoke check passed.")

    settings = dotenv_values(Path("infra/.env"))
    url = URL.create(
        "postgresql+asyncpg",
        username=settings["POSTGRES_USER"],
        password=settings["POSTGRES_PASSWORD"],
        host="127.0.0.1",
        port=int(settings.get("POSTGRES_PORT") or "5432"),
        database=settings["POSTGRES_DB"],
    )
    engine = create_async_engine(url, connect_args={"timeout": 10})
    try:
        async with engine.connect() as connection:
            assert await connection.scalar(select(1)) == 1
        print("PostgreSQL async connection check passed.")
    finally:
        await engine.dispose()


asyncio.run(main())
PY
