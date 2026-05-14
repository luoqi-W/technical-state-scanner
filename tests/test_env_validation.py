from technical_state_scanner.config import validate_longport_environment
from technical_state_scanner.loader import load_longport_credentials_from_env


def _clear_longport_env(monkeypatch):
    for name in [
        "LONGPORT_APP_KEY",
        "LONGPORT_APP_SECRET",
        "LONGPORT_ACCESS_TOKEN",
        "LONGBRIDGE_APP_KEY",
        "LONGBRIDGE_APP_SECRET",
        "LONGBRIDGE_ACCESS_TOKEN",
    ]:
        monkeypatch.delenv(name, raising=False)


def test_validation_reports_missing_env(monkeypatch):
    _clear_longport_env(monkeypatch)

    result = validate_longport_environment()

    assert result.ok is False
    assert any("Missing required LongPort environment variables" in e for e in result.errors)


def test_validation_accepts_longbridge_fallback_env_names(monkeypatch):
    _clear_longport_env(monkeypatch)
    monkeypatch.setattr("technical_state_scanner.config._is_longport_sdk_available", lambda: True)
    monkeypatch.setenv("LONGBRIDGE_APP_KEY", "fallback_key")
    monkeypatch.setenv("LONGBRIDGE_APP_SECRET", "fallback_secret")
    monkeypatch.setenv("LONGBRIDGE_ACCESS_TOKEN", "fallback_token")

    result = validate_longport_environment()

    assert result.ok is True
    assert result.errors == []


def test_loader_accepts_longbridge_fallback_env_names(monkeypatch):
    _clear_longport_env(monkeypatch)
    monkeypatch.setenv("LONGBRIDGE_APP_KEY", "fallback_key")
    monkeypatch.setenv("LONGBRIDGE_APP_SECRET", "fallback_secret")
    monkeypatch.setenv("LONGBRIDGE_ACCESS_TOKEN", "fallback_token")

    creds = load_longport_credentials_from_env()

    assert creds.app_key == "fallback_key"
    assert creds.app_secret == "fallback_secret"
    assert creds.access_token == "fallback_token"


def test_loader_prefers_longport_env_names(monkeypatch):
    _clear_longport_env(monkeypatch)
    monkeypatch.setenv("LONGPORT_APP_KEY", "preferred_key")
    monkeypatch.setenv("LONGPORT_APP_SECRET", "preferred_secret")
    monkeypatch.setenv("LONGPORT_ACCESS_TOKEN", "preferred_token")
    monkeypatch.setenv("LONGBRIDGE_APP_KEY", "fallback_key")
    monkeypatch.setenv("LONGBRIDGE_APP_SECRET", "fallback_secret")
    monkeypatch.setenv("LONGBRIDGE_ACCESS_TOKEN", "fallback_token")

    creds = load_longport_credentials_from_env()

    assert creds.app_key == "preferred_key"
    assert creds.app_secret == "preferred_secret"
    assert creds.access_token == "preferred_token"
