from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Sequence

from technical_state_scanner.config import validate_longport_environment
from technical_state_scanner.core.csv_output import (
    scan_result_to_structured_output,
    write_scan_results_to_csv,
    write_single_scan_result_to_json,
    write_universe_results_to_csv,
)
from technical_state_scanner.core.scanner import (
    LightweightUniverseResult,
    ScanResult,
    load_named_universe,
    load_symbols_from_file,
    scan_symbol,
    scan_universe_lightweight,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="LongPort multi-signal multi-timeframe technical state scanner."
    )
    subparsers = parser.add_subparsers(dest="command")

    subparsers.add_parser("validate-env", help="Check LongPort SDK and credential environment variables.")

    scan_parser = subparsers.add_parser("scan", help="Run a pure scanner job without chart rendering.")
    scan_target = scan_parser.add_mutually_exclusive_group(required=True)
    scan_target.add_argument("--ticker", help="Single ticker to scan, such as AAPL or AAPL.US.")
    scan_target.add_argument("--universe-file", help="CSV/TXT watchlist file containing symbols.")
    scan_target.add_argument(
        "--universe",
        choices=["sp500", "s&p500", "nasdaq", "nasdaq100"],
        help="Named local universe list to scan when available.",
    )
    scan_parser.add_argument("--symbol-column", help="CSV column name for --universe-file tickers.")
    scan_parser.add_argument("--count", type=int, default=700, help="Candlestick count per timeframe.")
    scan_parser.add_argument("--output", help="CSV output path. Defaults to reports/ when omitted.")
    scan_parser.add_argument("--json-output", help="JSON output path for structured scan data.")
    scan_parser.add_argument(
        "--no-charts",
        action="store_true",
        help="Pure scan mode. Accepted for clarity; CLI scans never render charts.",
    )
    return parser


def _print_env_validation() -> int:
    result = validate_longport_environment()
    if result.ok:
        print("LongPort environment validation passed.")
        return 0

    print("LongPort environment validation failed:")
    for err in result.errors:
        print(f"- {err}")
    return 1


def _print_single_summary(result: ScanResult, json_path: str | None, csv_path: str | None) -> None:
    print(f"Ticker: {result.ticker}")
    print(f"Total Score: {result.total_score:.1f}")
    print(f"Triggered Signals: {', '.join(result.all_triggered_signals) or 'None'}")
    if result.error:
        print(f"Failed Reason: {result.error}")
    if csv_path:
        print(f"CSV report: {csv_path}")
    if json_path:
        print(f"JSON report: {json_path}")


def _print_universe_summary(results: list[LightweightUniverseResult], csv_path: str | None, json_path: str | None) -> None:
    print(f"Scanned {len(results)} symbol(s).")
    for result in results[:10]:
        total_score = result.scores.get("total_score", 0.0)
        signals = ", ".join(result.triggered_signals) or "None"
        line = f"{result.ticker}: total_score={total_score:.1f}; signals={signals}"
        if result.error:
            line += f"; failed_reason={result.error}"
        print(line)
    if csv_path:
        print(f"CSV report: {csv_path}")
    if json_path:
        print(f"JSON report: {json_path}")


def _write_universe_json(results: list[LightweightUniverseResult], output_path: str) -> str:
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = [result.to_dict() for result in results]
    path.write_text(json.dumps(payload, indent=2, sort_keys=True, default=str), encoding="utf-8")
    return str(path)


def _run_single_scan(args: argparse.Namespace) -> int:
    result = scan_symbol(args.ticker, count=args.count)
    csv_path = write_scan_results_to_csv([result], output_path=args.output) if args.output else None
    json_path = write_single_scan_result_to_json(result, output_path=args.json_output) if args.json_output else None

    if not args.json_output:
        print(json.dumps(scan_result_to_structured_output(result), indent=2, sort_keys=True, default=str))
    _print_single_summary(result, json_path=json_path, csv_path=csv_path)
    return 1 if result.error else 0


def _load_universe_symbols(args: argparse.Namespace) -> list[str]:
    if args.universe_file:
        return load_symbols_from_file(args.universe_file, symbol_column=args.symbol_column)
    return load_named_universe(args.universe)


def _run_universe_scan(args: argparse.Namespace) -> int:
    symbols = _load_universe_symbols(args)
    results = scan_universe_lightweight(symbols, count=args.count)
    csv_path = write_universe_results_to_csv(results, output_path=args.output)
    json_path = _write_universe_json(results, args.json_output) if args.json_output else None
    _print_universe_summary(results, csv_path=csv_path, json_path=json_path)
    return 1 if any(result.error for result in results) else 0


def run_scan(args: argparse.Namespace) -> int:
    if args.no_charts:
        print("Pure scan mode: chart rendering is disabled.")

    if args.ticker:
        return _run_single_scan(args)
    return _run_universe_scan(args)


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.command == "validate-env":
        return _print_env_validation()
    if args.command == "scan":
        return run_scan(args)

    parser.print_help()
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
