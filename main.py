from __future__ import annotations

import argparse
import json
from pathlib import Path
from datetime import datetime
from typing import Sequence

from technical_state_scanner.loader import normalize_symbol
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
    load_universe_from_file,
    load_named_universe,
    load_symbols_from_file,
    scan_symbol,
    scan_universe_concurrent,
    scan_universe_lightweight,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="LongPort multi-signal multi-timeframe technical state scanner."
    )
    parser.add_argument("--universe", default="watchlist", help="Universe name or TXT file path for default scan.")
    parser.add_argument("--force-refresh", action="store_true", help="Bypass local parquet cache.")
    parser.add_argument("--workers", type=int, default=3, help="Concurrent workers for universe scans.")
    parser.add_argument("--count", type=int, default=700, help="Candlestick count per timeframe.")
    subparsers = parser.add_subparsers(dest="command")

    subparsers.add_parser("validate-env", help="Check LongPort SDK and credential environment variables.")

    scan_parser = subparsers.add_parser("scan", help="Run a pure scanner job without chart rendering.")
    scan_target = scan_parser.add_mutually_exclusive_group(required=True)
    scan_target.add_argument("--ticker", help="Single ticker to scan, such as AAPL or AAPL.US.")
    scan_target.add_argument("--universe-file", help="CSV/TXT watchlist file containing symbols.")
    scan_target.add_argument(
        "--universe",
        choices=["watchlist", "sp100", "sp500", "s&p500", "nasdaq", "nasdaq100"],
        help="Named local universe list to scan when available.",
    )
    scan_parser.add_argument("--symbol-column", help="CSV column name for --universe-file tickers.")
    scan_parser.add_argument("--count", type=int, default=700, help="Candlestick count per timeframe.")
    scan_parser.add_argument("--workers", type=int, default=3, help="Concurrent workers for universe scans.")
    scan_parser.add_argument("--force-refresh", action="store_true", help="Bypass local parquet cache.")
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


def write_universe_json(results: list[LightweightUniverseResult], output_path: str) -> str:
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = [result.to_dict() for result in results]
    path.write_text(json.dumps(payload, indent=2, sort_keys=True, default=str), encoding="utf-8")
    return str(path)


def resolve_universe_symbols(
    universe_file: str | None = None,
    universe_name: str | None = None,
    symbol_column: str | None = None,
) -> list[str]:
    if universe_file:
        return load_symbols_from_file(universe_file, symbol_column=symbol_column)
    if universe_name:
        return load_named_universe(universe_name)
    raise ValueError("Either universe_file or universe_name must be provided.")


def resolve_default_universe_symbols(universe: str) -> list[str]:
    candidate = Path(universe)
    if candidate.exists():
        return load_universe_from_file(candidate)
    named_path = Path("universes") / f"{universe}.txt"
    if named_path.exists():
        return load_universe_from_file(named_path)
    return load_named_universe(universe)


def execute_single_scan(
    ticker: str,
    count: int = 700,
    output: str | None = None,
    json_output: str | None = None,
) -> tuple[ScanResult, str | None, str | None]:
    result = scan_symbol(ticker, count=count)
    csv_path = write_scan_results_to_csv([result], output_path=output) if output else None
    json_path = write_single_scan_result_to_json(result, output_path=json_output) if json_output else None
    return result, csv_path, json_path


def execute_universe_scan(
    symbols: list[str],
    count: int = 700,
    output: str | None = None,
    json_output: str | None = None,
) -> tuple[list[LightweightUniverseResult], str | None, str | None]:
    results = scan_universe_lightweight(symbols, count=count)
    csv_path = write_universe_results_to_csv(results, output_path=output)
    json_path = write_universe_json(results, json_output) if json_output else None
    return results, csv_path, json_path


def execute_concurrent_universe_scan(
    symbols: list[str],
    count: int = 700,
    workers: int = 3,
    force_refresh: bool = False,
    output: str | None = None,
) -> tuple[list[ScanResult], str]:
    def _progress(completed: int, total: int, current_symbol: str) -> None:
        print(f"[{completed}/{total}] {current_symbol}")

    results = scan_universe_concurrent(
        symbols=symbols,
        count=count,
        max_workers=workers,
        force_refresh=force_refresh,
        on_progress=_progress,
    )
    if output is None:
        Path("reports").mkdir(parents=True, exist_ok=True)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        output = str(Path("reports") / f"scan_{timestamp}.csv")
    csv_path = write_scan_results_to_csv(results, output_path=output)
    return results, csv_path


def _run_single_scan(args: argparse.Namespace) -> int:
    result, csv_path, json_path = execute_single_scan(
        ticker=args.ticker,
        count=args.count,
        output=args.output,
        json_output=args.json_output,
    )
    if not args.json_output:
        print(json.dumps(scan_result_to_structured_output(result), indent=2, sort_keys=True, default=str))
    _print_single_summary(result, json_path=json_path, csv_path=csv_path)
    return 1 if result.error else 0


def _run_universe_scan(args: argparse.Namespace) -> int:
    symbols = resolve_universe_symbols(
        universe_file=args.universe_file,
        universe_name=args.universe,
        symbol_column=args.symbol_column,
    )
    if args.force_refresh or args.workers != 3:
        results, csv_path = execute_concurrent_universe_scan(
            symbols=symbols,
            count=args.count,
            workers=args.workers,
            force_refresh=args.force_refresh,
            output=args.output,
        )
        _print_ranked_summary(results, csv_path)
        return 1 if any(r.error for r in results) else 0

    results, csv_path, json_path = execute_universe_scan(
        symbols=symbols,
        count=args.count,
        output=args.output,
        json_output=args.json_output,
    )
    _print_universe_summary(results, csv_path=csv_path, json_path=json_path)
    return 1 if any(r.error for r in results) else 0


def _print_ranked_summary(results: list[ScanResult], csv_path: str) -> None:
    print(f"CSV report: {csv_path}")
    print("Top 10 by total_score:")
    print("ticker,total_score,signals,error")
    for result in results[:10]:
        signals = ";".join(result.all_triggered_signals) or "None"
        print(f"{result.ticker},{result.total_score:.1f},{signals},{result.error or 'None'}")


def run_default_universe_scan(args: argparse.Namespace) -> int:
    symbols = resolve_default_universe_symbols(args.universe)
    print(
        f"Scanning {len(symbols)} symbols from universe `{args.universe}` "
        f"(count={args.count}, workers={args.workers}, force_refresh={args.force_refresh})"
    )
    results, csv_path = execute_concurrent_universe_scan(
        symbols=symbols,
        count=args.count,
        workers=args.workers,
        force_refresh=args.force_refresh,
    )
    _print_ranked_summary(results, csv_path)
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

    return run_default_universe_scan(args)


if __name__ == "__main__":
    raise SystemExit(main())
