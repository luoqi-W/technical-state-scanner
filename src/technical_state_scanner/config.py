"""Configuration and environment validation for LongPort access."""

from __future__ import annotations

from dataclasses import dataclass
import importlib.util
import os
from typing import List


REQUIRED_ENV_VARS = (
    "LONGPORT_APP_KEY",
    "LONGPORT_APP_SECRET",
    "LONGPORT_ACCESS_TOKEN",
)

FALLBACK_ENV_VARS = (
    "LONGBRIDGE_APP_KEY",
    "LONGBRIDGE_APP_SECRET",
    "LONGBRIDGE_ACCESS_TOKEN",
)

ENV_VAR_GROUPS = tuple(zip(REQUIRED_ENV_VARS, FALLBACK_ENV_VARS))


@dataclass(frozen=True)
class ValidationResult:
    """Result of LongPort environment and SDK validation."""

    ok: bool
    errors: List[str]


def _is_longport_sdk_available() -> bool:
    try:
        return importlib.util.find_spec("longport.openapi") is not None
    except ModuleNotFoundError:
        return False


def get_longport_env_value(preferred_name: str, fallback_name: str) -> str | None:
    """Return a credential value, preferring LONGPORT_* over LONGBRIDGE_*."""

    return os.getenv(preferred_name) or os.getenv(fallback_name)


def get_missing_longport_env_groups() -> list[str]:
    """Return credential groups where neither accepted env var name is set."""

    missing: list[str] = []
    for preferred_name, fallback_name in ENV_VAR_GROUPS:
        if not get_longport_env_value(preferred_name, fallback_name):
            missing.append(f"{preferred_name} or {fallback_name}")
    return missing


def validate_longport_environment() -> ValidationResult:
    """Validate LongPort SDK availability and required credentials."""

    errors: List[str] = []

    if not _is_longport_sdk_available():
        errors.append(
            "LongPort SDK is not installed or not importable. Install dependency `longport`."
        )

    missing = get_missing_longport_env_groups()
    if missing:
        errors.append(
            "Missing required LongPort environment variables: " + ", ".join(missing)
        )

    return ValidationResult(ok=len(errors) == 0, errors=errors)
