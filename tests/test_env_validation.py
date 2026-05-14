from technical_state_scanner.config import validate_longport_environment


def test_validation_reports_missing_env(monkeypatch):
    monkeypatch.delenv("LONGPORT_APP_KEY", raising=False)
    monkeypatch.delenv("LONGPORT_APP_SECRET", raising=False)
    monkeypatch.delenv("LONGPORT_ACCESS_TOKEN", raising=False)

    result = validate_longport_environment()

    assert result.ok is False
    assert any("Missing required LongPort environment variables" in e for e in result.errors)
