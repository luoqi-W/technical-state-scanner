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


def validate_longport_environment() -> ValidationResult:
    """Validate LongPort SDK availability and required credentials."""

    errors: List[str] = []

    if not _is_longport_sdk_available():
        errors.append(
            "LongPort SDK is not installed or not importable. Install dependency `longport`."
        )

    missing = [var for var in REQUIRED_ENV_VARS if not os.getenv(var)]
    if missing:
        errors.append(
            "Missing required LongPort environment variables: " + ", ".join(missing)
        )

    return ValidationResult(ok=len(errors) == 0, errors=errors)
