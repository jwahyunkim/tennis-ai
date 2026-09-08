import pytest

from backend.tests.conftest import _require_test_database


@pytest.mark.parametrize(
    "name",
    [
        "tennis_ai",
        "production",
        "tennis_ai_test; DROP DATABASE tennis_ai",
        'tennis_ai_test"',
        "../tennis_ai_test",
        "x" * 59 + "_test",
    ],
)
def test_database_cleanup_rejects_unsafe_targets(monkeypatch, name):
    monkeypatch.setenv("RUN_DB_TESTS", "1")
    with pytest.raises(ValueError, match="ending in _test"):
        _require_test_database(name)


def test_database_cleanup_requires_explicit_opt_in(monkeypatch):
    monkeypatch.delenv("RUN_DB_TESTS", raising=False)
    with pytest.raises(pytest.skip.Exception):
        _require_test_database("tennis_ai_test")


def test_database_cleanup_accepts_dedicated_test_target(monkeypatch):
    monkeypatch.setenv("RUN_DB_TESTS", "1")
    _require_test_database("tennis_ai_test")
