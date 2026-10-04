import pytest
from pydantic import ValidationError

from stylesense.platform.config import Environment, Settings, get_settings
from tests.factories import make_settings


def test_builds_with_required_values_and_safe_defaults() -> None:
    settings = make_settings()

    assert settings.env is Environment.TEST
    assert settings.debug is False
    assert settings.db_pool_size == 10
    assert settings.readiness_timeout_s == 2.0


def test_reads_values_from_prefixed_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("APP_ENV", "staging")
    monkeypatch.setenv("APP_DATABASE_URL", "postgresql+asyncpg://u:p@db:5432/x")
    monkeypatch.setenv("APP_REDIS_URL", "redis://cache:6379/0")
    monkeypatch.setenv("APP_DB_POOL_SIZE", "25")
    monkeypatch.setenv("APP_JWT_SECRET", "x" * 32)
    monkeypatch.setenv("APP_GOOGLE_CLIENT_IDS", '["a.apps.googleusercontent.com"]')

    settings = Settings(_env_file=None)

    assert settings.env is Environment.STAGING
    assert settings.db_pool_size == 25
    assert settings.redis_url.host == "cache"


@pytest.mark.parametrize("missing", ["database_url", "redis_url", "jwt_secret"])
def test_fails_fast_when_required_value_missing(
    missing: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("APP_DATABASE_URL", raising=False)
    monkeypatch.delenv("APP_REDIS_URL", raising=False)
    values = {
        "database_url": "postgresql+asyncpg://u:p@h/db",
        "redis_url": "redis://h:6379/0",
        "jwt_secret": "x" * 32,
    }
    del values[missing]

    with pytest.raises(ValidationError, match=missing):
        Settings(_env_file=None, **values)  # type: ignore[arg-type]


def test_rejects_sync_postgres_driver() -> None:
    with pytest.raises(ValidationError, match="asyncpg"):
        make_settings(database_url="postgresql://u:p@h/db")


def test_rejects_non_postgres_database() -> None:
    with pytest.raises(ValidationError):
        make_settings(database_url="mysql://u:p@h/db")


def test_rejects_debug_in_production() -> None:
    with pytest.raises(ValidationError, match="debug"):
        make_settings(env="production", debug=True)


def test_rejects_unknown_environment() -> None:
    with pytest.raises(ValidationError):
        make_settings(env="qa")


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("db_pool_size", 0),
        ("db_pool_size", 101),
        ("db_max_overflow", -1),
        ("db_statement_timeout_ms", 50),
        ("readiness_timeout_s", 0),
        ("readiness_timeout_s", 11),
        ("log_level", "VERBOSE"),
    ],
)
def test_rejects_out_of_range_values(field: str, value: object) -> None:
    with pytest.raises(ValidationError, match=field):
        make_settings(**{field: value})


@pytest.mark.parametrize(
    ("env", "expected"),
    [("local", True), ("test", True), ("staging", True), ("production", False)],
)
def test_api_docs_hidden_only_in_production(env: str, expected: bool) -> None:
    assert make_settings(env=env).docs_enabled is expected


def test_settings_are_immutable() -> None:
    settings = make_settings()

    with pytest.raises(ValidationError):
        settings.debug = True  # type: ignore[misc]


def test_get_settings_is_cached(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("APP_DATABASE_URL", "postgresql+asyncpg://u:p@h/db")
    monkeypatch.setenv("APP_REDIS_URL", "redis://h:6379/0")
    monkeypatch.setenv("APP_JWT_SECRET", "x" * 32)
    get_settings.cache_clear()

    assert get_settings() is get_settings()
    get_settings.cache_clear()


def test_reads_list_values_from_json_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("APP_DATABASE_URL", "postgresql+asyncpg://u:p@h/db")
    monkeypatch.setenv("APP_REDIS_URL", "redis://h:6379/0")
    monkeypatch.setenv("APP_JWT_SECRET", "x" * 32)
    monkeypatch.setenv("APP_ADMIN_EMAILS", '[" Founder@StyleSense.app "]')

    assert Settings(_env_file=None).admin_emails == ["founder@stylesense.app"]


def test_rejects_short_jwt_secret() -> None:
    with pytest.raises(ValidationError, match="jwt_secret"):
        make_settings(jwt_secret="too-short")


def test_jwt_secret_is_never_printed() -> None:
    settings = make_settings()

    assert settings.jwt_secret.get_secret_value() not in repr(settings)


def test_production_requires_google_client_ids() -> None:
    with pytest.raises(ValidationError, match="google_client_ids"):
        make_settings(env="production", google_client_ids=[])


@pytest.mark.parametrize("version", ["1.2", "v1.2.3", "1.2.3-beta"])
def test_rejects_malformed_app_versions(version: str) -> None:
    with pytest.raises(ValidationError, match="min_supported_app_version"):
        make_settings(min_supported_app_version=version)
