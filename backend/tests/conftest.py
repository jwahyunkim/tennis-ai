import os

import pytest

from backend.core.config import Settings


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
