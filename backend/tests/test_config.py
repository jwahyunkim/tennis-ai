import pytest
from pydantic import ValidationError

from backend.core.config import Settings


def test_database_url_preserves_special_characters(clean_database_environment):
    password = "test:p@ss/word?#%"
    settings = Settings(_env_file=None, postgres_password=password)

    assert settings.database_url.drivername == "postgresql+asyncpg"
    assert settings.database_url.host == "127.0.0.1"
    assert settings.database_url.port == 5432
    assert settings.database_url.database == "tennis_ai"
    assert settings.database_url.username == "tennis_ai"
    assert settings.database_url.password == password
    assert password not in repr(settings)
    assert password not in str(settings.database_url)


def test_environment_overrides_env_file(
    clean_database_environment, monkeypatch, tmp_path
):
    env_file = tmp_path / ".env"
    env_file.write_text(
        "POSTGRES_PASSWORD=file-password\n"
        "POSTGRES_DB=file_database\n"
        "POSTGRES_PORT=5433\n"
        "OTHER_SERVICE_SETTING=ignored\n"
    )
    monkeypatch.setenv("POSTGRES_PORT", "6543")
    monkeypatch.setenv("POSTGRES_PASSWORD", "environment-password")

    settings = Settings(_env_file=env_file)

    assert settings.postgres_db == "file_database"
    assert settings.postgres_port == 6543
    assert settings.postgres_password.get_secret_value() == "environment-password"


def test_database_password_is_required(clean_database_environment):
    with pytest.raises(ValidationError):
        Settings(_env_file=None)


@pytest.mark.parametrize("field", ["postgres_db", "postgres_user", "postgres_password"])
def test_database_credentials_cannot_be_empty(clean_database_environment, field):
    values = {"postgres_password": "test-only-password", field: ""}

    with pytest.raises(ValidationError):
        Settings(_env_file=None, **values)


@pytest.mark.parametrize("port", [0, -1, 65536])
def test_database_port_range_is_validated(clean_database_environment, port):
    with pytest.raises(ValidationError):
        Settings(_env_file=None, postgres_password="test-only", postgres_port=port)


@pytest.mark.parametrize("timeout", [0, -1, 61])
def test_database_timeout_range_is_validated(clean_database_environment, timeout):
    with pytest.raises(ValidationError):
        Settings(
            _env_file=None,
            postgres_password="test-only",
            database_timeout_seconds=timeout,
        )


def test_settings_validation_errors_hide_input(clean_database_environment):
    sensitive_input = "do-not-print-this-input"

    with pytest.raises(ValidationError) as error:
        Settings(
            _env_file=None,
            postgres_password="test-only",
            postgres_port=sensitive_input,
        )

    assert sensitive_input not in str(error.value)
