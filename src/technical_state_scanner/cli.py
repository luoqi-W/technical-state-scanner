"""CLI entrypoints for technical-state-scanner."""

from __future__ import annotations

import sys

from technical_state_scanner.config import validate_longport_environment


def main() -> int:
    result = validate_longport_environment()
    if result.ok:
        print("LongPort environment validation passed.")
        return 0

    print("LongPort environment validation failed:")
    for err in result.errors:
        print(f"- {err}")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
