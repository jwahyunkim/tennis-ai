import asyncio
import json
import os
import re
import struct
import subprocess
import sys
from pathlib import Path

import asyncpg
import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import delete

from backend.core.config import Settings
from backend.models.base import Base


@pytest.fixture
def clean_database_environment(monkeypatch):
    for name in os.environ:
        if (
            name.upper().startswith("POSTGRES_")
            or name.upper() == "DATABASE_TIMEOUT_SECONDS"
        ):
            monkeypatch.delenv(name)


@pytest.fixture
def settings(clean_database_environment):
    return Settings(_env_file=None, postgres_password="test-only-password")


def pytest_collection_modifyitems(items):
    if os.environ.get("RUN_DB_TESTS") == "1":
        return
    skip_integration = pytest.mark.skip(reason="Set RUN_DB_TESTS=1 to use PostgreSQL")
    for item in items:
        if "integration" in item.keywords:
            item.add_marker(skip_integration)


def _require_test_database(database_name: str) -> None:
    if os.environ.get("RUN_DB_TESTS") != "1":
        pytest.skip("Set RUN_DB_TESTS=1 to use PostgreSQL")
    if re.fullmatch(r"[a-z][a-z0-9_]{0,57}_test", database_name) is None:
        raise ValueError(
            "Integration database must be a safe identifier ending in _test"
        )


async def _ensure_test_database(settings: Settings, source_database: str) -> None:
    _require_test_database(settings.postgres_db)
    arguments = {
        "host": settings.postgres_host,
        "port": settings.postgres_port,
        "user": settings.postgres_user,
        "password": settings.postgres_password.get_secret_value(),
        "timeout": settings.database_timeout_seconds,
    }
    try:
        connection = await asyncpg.connect(database=settings.postgres_db, **arguments)
    except asyncpg.InvalidCatalogNameError:
        connection = await asyncpg.connect(database=source_database, **arguments)
        try:
            # Database creation is outside Alembic's schema operations and cannot
            # be parameterized. The identifier is strictly checked immediately above.
            await connection.execute(f'CREATE DATABASE "{settings.postgres_db}"')
        except asyncpg.DuplicateDatabaseError:
            pass
        finally:
            await connection.close()
    else:
        await connection.close()


@pytest.fixture(scope="session")
def migrated_test_settings():
    source_settings = Settings()
    default_database = (
        source_settings.postgres_db
        if source_settings.postgres_db.endswith("_test")
        else "tennis_ai_test"
    )
    database = os.environ.get("POSTGRES_TEST_DB", default_database)
    _require_test_database(database)
    test_settings = source_settings.model_copy(update={"postgres_db": database})
    asyncio.run(_ensure_test_database(test_settings, source_settings.postgres_db))

    repository_root = Path(__file__).resolve().parents[2]
    environment = os.environ.copy()
    environment["POSTGRES_DB"] = database
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "alembic",
            "-c",
            str(repository_root / "backend" / "alembic.ini"),
            "upgrade",
            "head",
        ],
        cwd=repository_root,
        env=environment,
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )
    if result.returncode != 0:
        output = (result.stdout + result.stderr).replace(
            test_settings.postgres_password.get_secret_value(), "[REDACTED]"
        )
        pytest.fail(f"Isolated test database migration failed:\n{output}")
    return test_settings


@pytest.fixture
def integration_settings(migrated_test_settings, tmp_path):
    return migrated_test_settings.model_copy(
        update={
            "storage_backend": "local",
            "storage_local_path": tmp_path / "media",
            "auth_max_attempts": 3,
            "database_timeout_seconds": 10,
            "worker_heartbeat_path": tmp_path / "worker-heartbeat",
        }
    )


@pytest.fixture
async def api_app(integration_settings):
    from backend.main import create_app

    _require_test_database(integration_settings.postgres_db)
    app = create_app(integration_settings)

    async def clear_test_rows():
        # Guard at the deletion boundary, even if a fixture is later overridden.
        _require_test_database(app.state.settings.postgres_db)
        async with app.state.session_factory() as session:
            for table in reversed(Base.metadata.sorted_tables):
                await session.execute(delete(table))
            await session.commit()

    async with app.router.lifespan_context(app):
        await clear_test_rows()
        try:
            yield app
        finally:
            await clear_test_rows()


@pytest.fixture
async def api_client(api_app):
    async with AsyncClient(
        transport=ASGITransport(app=api_app), base_url="http://test"
    ) as client:
        yield client


@pytest.fixture(scope="session")
def small_video_bytes(tmp_path_factory):
    path = tmp_path_factory.mktemp("media-fixtures") / "sample.mp4"
    subprocess.run(
        [
            "ffmpeg",
            "-v",
            "error",
            "-f",
            "lavfi",
            "-i",
            "color=c=blue:s=64x64:r=10",
            "-t",
            "0.4",
            "-c:v",
            "libx264",
            "-pix_fmt",
            "yuv420p",
            "-movflags",
            "+faststart",
            str(path),
        ],
        capture_output=True,
        check=True,
        timeout=20,
    )
    return path.read_bytes()


@pytest.fixture
def triangle_glb_bytes():
    # A standards-shaped triangle is test data for the adapter boundary, not a
    # stand-in body model returned by application code.
    positions = struct.pack("<9f", 0, 0, 0, 1, 0, 0, 0, 1, 0)
    document = {
        "asset": {"version": "2.0"},
        "scene": 0,
        "scenes": [{"nodes": [0]}],
        "nodes": [{"mesh": 0}],
        "meshes": [{"primitives": [{"attributes": {"POSITION": 0}}]}],
        "buffers": [{"byteLength": len(positions)}],
        "bufferViews": [{"buffer": 0, "byteLength": len(positions), "target": 34962}],
        "accessors": [
            {
                "bufferView": 0,
                "componentType": 5126,
                "count": 3,
                "type": "VEC3",
                "min": [0, 0, 0],
                "max": [1, 1, 0],
            }
        ],
    }
    encoded = json.dumps(document).encode()
    encoded += b" " * (-len(encoded) % 4)
    total = 12 + 8 + len(encoded) + 8 + len(positions)
    return (
        struct.pack("<4sII", b"glTF", 2, total)
        + struct.pack("<I4s", len(encoded), b"JSON")
        + encoded
        + struct.pack("<I4s", len(positions), b"BIN\0")
        + positions
    )
