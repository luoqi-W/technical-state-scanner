"""Scanner module for single-stock and universe scans."""

from __future__ import annotations

from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, asdict
from pathlib import Path
import sys
import time
from typing import Any

import pandas as pd

from technical_state_scanner.loader import load_multi_timeframe_ohlcv, load_multi_timeframe_ohlcv_smart, normalize_symbol
from technical_state_scanner.core.signal_aggregator import aggregate_signals_with_scoring


@dataclass
class ScanResult:
    """Result of scanning a single stock."""

    ticker: str
    total_score: float
    pre_multiplier_score: float
    cross_timeframe_all_factor_coverage_multiplier: float
    all_triggered_signals: list[str]
    base_timeframe_scores: dict[str, Any]
    factor_confluence_scores: dict[str, Any]
    timeframe_results: dict[str, dict[str, Any]]
    notes: list[str]
    data_source: str = "LongPort OpenAPI"
    error: str | None = None


@dataclass
class LightweightUniverseResult:
    """Lightweight result intended for ranked universe browsing.

    This intentionally excludes factor diagnostic details and chart data. The UI can
    lazily run a detailed single-stock scan or load chart data after a ticker is
    selected.
    """

    ticker: str
    scores: dict[str, Any]
    triggered_signals: list[str]
    triggered_factors: list[str]
    timeframe_triggered_signals: dict[str, list[str]]
    timeframe_triggered_factors: dict[str, list[str]]
    factor_confluence: dict[str, Any]
    timestamps: dict[str, Any]
    data_source: str = "LongPort OpenAPI"
    error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-like dictionary for UI tables or API-style output."""

        return asdict(self)


def scan_symbol(
    symbol: str,
    count: int = 300,
) -> ScanResult:
    """Scan a single stock symbol across all timeframes.
    
    Args:
        symbol: Stock symbol (e.g., 'AAPL' or 'AAPL.US')
        count: Number of candlesticks to load per timeframe (default: 300)
        
    Returns:
        ScanResult with complete scoring and signal analysis
    """
    result, _frames = scan_symbol_with_frames(symbol=symbol, count=count)
    return result


def _empty_error_result(symbol: str, message: str) -> ScanResult:
    return ScanResult(
        ticker=symbol,
        total_score=0.0,
        pre_multiplier_score=0.0,
        cross_timeframe_all_factor_coverage_multiplier=1.0,
        all_triggered_signals=[],
        base_timeframe_scores={},
        factor_confluence_scores={},
        timeframe_results={},
        notes=[message],
        error=message,
    )


def _build_scan_result_from_aggregation(
    symbol: str,
    agg_result: dict[str, Any],
    statuses: dict[str, Any],
) -> ScanResult:
    notes = []
    for timeframe, status in statuses.items():
        if not status.ok:
            notes.append(f"{timeframe}: {status.reason}")

    # Extract scoring
    scoring = agg_result.get("scoring", {})

    # Compile timeframe results with full details
    timeframe_results = {}
    for timeframe in ["weekly", "daily", "4hour"]:
        tf_data = agg_result.get("timeframes", {}).get(timeframe, {})
        timeframe_results[timeframe] = {
            "triggered_signals": tf_data.get("triggered_signals", []),
            "triggered_factors": tf_data.get("triggered_factors", []),
            "factor_confluence_tier": scoring.get("factor_confluence_scores", {}).get(timeframe, {}).get("tier"),
            "factor_confluence_score": scoring.get("factor_confluence_scores", {}).get(timeframe, {}).get("score", 0),
            "details": tf_data.get("details", {}),
        }

    # Add notes about signal detection
    triggered_signals = agg_result.get("triggered_signals", [])
    if not triggered_signals:
        notes.append("No technical signals detected across all timeframes.")
    else:
        notes.append(f"Detected {len(set(triggered_signals))} unique signals across {len([tf for tf in timeframe_results if timeframe_results[tf]['triggered_signals']])} timeframes.")

    # Add note about signal independence
    notes.append("Signals are independent; this output does not imply sequential stage progression.")
    notes.append("No factor priority is applied; all triggered signals are listed.")

    return ScanResult(
        ticker=symbol,
        total_score=scoring.get("total_score", 0.0),
        pre_multiplier_score=scoring.get("pre_multiplier_score", 0.0),
        cross_timeframe_all_factor_coverage_multiplier=scoring.get("cross_timeframe_all_factor_coverage_multiplier", 1.0),
        all_triggered_signals=triggered_signals,
        base_timeframe_scores=scoring.get("base_timeframe_scores", {}),
        factor_confluence_scores=scoring.get("factor_confluence_scores", {}),
        timeframe_results=timeframe_results,
        notes=notes,
    )


def scan_symbol_with_frames(
    symbol: str,
    count: int = 300,
) -> tuple[ScanResult, dict[str, pd.DataFrame]]:
    """Scan a symbol and return both scanner result and loaded OHLCV frames."""

    symbol = normalize_symbol(symbol)
    try:
        frames, statuses = load_multi_timeframe_ohlcv(symbol=symbol, count=count)
    except Exception as exc:
        return _empty_error_result(symbol, str(exc)), {}

    try:
        agg_result = aggregate_signals_with_scoring(frames)
    except Exception as exc:
        return _empty_error_result(symbol, f"Signal aggregation failed: {str(exc)}"), frames

    return _build_scan_result_from_aggregation(symbol, agg_result, statuses), frames


def scan_symbol_with_frames_smart(
    symbol: str,
    count: int = 700,
    force_refresh: bool = False,
) -> tuple[ScanResult, dict[str, pd.DataFrame]]:
    """Scan a symbol using the cache-first LongPort loader."""

    symbol = normalize_symbol(symbol)
    try:
        frames, statuses = load_multi_timeframe_ohlcv_smart(
            symbol=symbol,
            count=count,
            force_refresh=force_refresh,
        )
    except Exception as exc:
        return _empty_error_result(symbol, str(exc)), {}

    try:
        agg_result = aggregate_signals_with_scoring(frames)
    except Exception as exc:
        return _empty_error_result(symbol, f"Signal aggregation failed: {str(exc)}"), frames

    return _build_scan_result_from_aggregation(symbol, agg_result, statuses), frames


def scan_symbol_smart(
    symbol: str,
    count: int = 700,
    force_refresh: bool = False,
) -> ScanResult:
    """Scan a single symbol using cache-first loading."""

    result, _frames = scan_symbol_with_frames_smart(symbol, count=count, force_refresh=force_refresh)
    return result


def _extract_universe_timestamps(result: ScanResult) -> dict[str, dict[str, str | None]]:
    timestamps: dict[str, dict[str, str | None]] = {}
    for timeframe, timeframe_result in result.timeframe_results.items():
        timestamps[timeframe] = {}
        for factor_id, factor_result in timeframe_result.get("details", {}).items():
            if factor_id in timeframe_result.get("triggered_factors", []):
                timestamps[timeframe][factor_id] = factor_result.get("timestamp")
    return timestamps


def _to_lightweight_universe_result(result: ScanResult) -> LightweightUniverseResult:
    triggered_factors: list[str] = []
    for timeframe_result in result.timeframe_results.values():
        for factor_id in timeframe_result.get("triggered_factors", []):
            if factor_id not in triggered_factors:
                triggered_factors.append(factor_id)

    return LightweightUniverseResult(
        ticker=result.ticker,
        scores={
            "total_score": result.total_score,
            "pre_multiplier_score": result.pre_multiplier_score,
            "cross_timeframe_all_factor_coverage_multiplier": result.cross_timeframe_all_factor_coverage_multiplier,
            "base_timeframe_scores": result.base_timeframe_scores,
        },
        triggered_signals=result.all_triggered_signals,
        triggered_factors=triggered_factors,
        timeframe_triggered_signals={
            timeframe: timeframe_result.get("triggered_signals", [])
            for timeframe, timeframe_result in result.timeframe_results.items()
        },
        timeframe_triggered_factors={
            timeframe: timeframe_result.get("triggered_factors", [])
            for timeframe, timeframe_result in result.timeframe_results.items()
        },
        factor_confluence=result.factor_confluence_scores,
        timestamps=_extract_universe_timestamps(result),
        error=result.error,
    )


def scan_universe(
    symbols: list[str],
    count: int = 300,
) -> list[ScanResult]:
    """Scan multiple stock symbols.
    
    Args:
        symbols: List of stock symbols
        count: Number of candlesticks to load per timeframe (default: 300)
        
    Returns:
        List of ScanResult for each symbol
    """
    results = []
    for symbol in symbols:
        result = scan_symbol(symbol, count=count)
        results.append(result)
    return results


def scan_universe_lightweight(
    symbols: list[str],
    count: int = 300,
) -> list[LightweightUniverseResult]:
    """Scan multiple symbols and keep only lightweight structured results.

    The returned objects contain ranking and signal summary fields only:
    ticker, scores, triggered signals/factors, confluence, and timestamps.
    No chart data or full factor diagnostic payload is retained.
    """

    detailed_results = scan_universe(symbols=symbols, count=count)
    lightweight = [_to_lightweight_universe_result(result) for result in detailed_results]
    return sorted(
        lightweight,
        key=lambda item: float(item.scores.get("total_score", 0.0)),
        reverse=True,
    )


def load_universe_from_file(path: str | Path) -> list[str]:
    """Read normalized tickers from a TXT universe file."""

    universe_path = Path(path)
    if not universe_path.exists():
        raise FileNotFoundError(f"Universe file not found: {universe_path}")
    symbols: list[str] = []
    for line in universe_path.read_text(encoding="utf-8").splitlines():
        text = line.strip()
        if not text or text.startswith("#"):
            continue
        normalized = normalize_symbol(text)
        if normalized not in symbols:
            symbols.append(normalized)
    if not symbols:
        raise ValueError(f"Universe file contains no usable tickers: {universe_path}")
    return symbols


def scan_universe_concurrent(
    symbols: list[str],
    count: int = 700,
    max_workers: int = 3,
    force_refresh: bool = False,
    on_progress: Callable[[int, int, str], None] | None = None,
) -> list[ScanResult]:
    """Scan multiple symbols concurrently using the smart cache loader."""

    if max_workers < 1:
        raise ValueError("max_workers must be at least 1.")

    normalized_symbols = []
    for symbol in symbols:
        normalized = normalize_symbol(symbol)
        if normalized not in normalized_symbols:
            normalized_symbols.append(normalized)

    total = len(normalized_symbols)
    results: list[ScanResult] = []
    completed = 0

    def _scan(symbol: str) -> ScanResult:
        try:
            return scan_symbol_smart(symbol, count=count, force_refresh=force_refresh)
        except Exception as exc:  # pragma: no cover - defensive concurrent path
            print(f"Failed to scan {symbol}: {exc}", file=sys.stderr)
            return _empty_error_result(symbol, str(exc))

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {}
        for symbol in normalized_symbols:
            futures[executor.submit(_scan, symbol)] = symbol
            time.sleep(0.2)

        for future in as_completed(futures):
            symbol = futures[future]
            try:
                result = future.result()
            except Exception as exc:  # pragma: no cover - defensive concurrent path
                print(f"Failed to scan {symbol}: {exc}", file=sys.stderr)
                result = _empty_error_result(symbol, str(exc))
            results.append(result)
            completed += 1
            if on_progress is not None:
                on_progress(completed, total, symbol)

    return sorted(results, key=lambda item: item.total_score, reverse=True)


def load_symbols_from_file(path: str | Path, symbol_column: str | None = None) -> list[str]:
    """Load symbols from a CSV or TXT watchlist and normalize them for LongPort.

    TXT/LIST files may contain one symbol per line or comma-separated symbols.
    Blank lines and lines starting with ``#`` are ignored. CSV files use
    ``symbol_column`` when provided; otherwise the first column is treated as the
    ticker column.
    """

    watchlist_path = Path(path)
    if not watchlist_path.exists():
        raise FileNotFoundError(f"Symbol list file not found: {watchlist_path}")

    suffix = watchlist_path.suffix.lower()
    if suffix == ".csv":
        df = pd.read_csv(watchlist_path)
        if df.empty:
            raise ValueError(f"Symbol list CSV is empty: {watchlist_path}")
        column = symbol_column or str(df.columns[0])
        if column not in df.columns:
            raise ValueError(f"Symbol column `{column}` not found in {watchlist_path}")
        raw_symbols = [str(value).strip() for value in df[column].dropna().tolist()]
    elif suffix in {".txt", ".list"}:
        raw_symbols = []
        for line in watchlist_path.read_text(encoding="utf-8").splitlines():
            text = line.strip()
            if text and not text.startswith("#"):
                raw_symbols.extend(symbol.strip() for symbol in text.split(",") if symbol.strip())
    else:
        raise ValueError("Symbol list must be a .csv, .txt, or .list file.")

    normalized: list[str] = []
    for symbol in raw_symbols:
        normalized_symbol = normalize_symbol(symbol)
        if normalized_symbol not in normalized:
            normalized.append(normalized_symbol)
    if not normalized:
        raise ValueError(f"Symbol list contains no usable tickers: {watchlist_path}")
    return normalized


def load_named_universe(name: str, base_path: str | Path = ".") -> list[str]:
    """Load an S&P-style or Nasdaq-style local universe list when available."""

    aliases = {
        "watchlist": "watchlist",
        "sp100": "sp100",
        "sp500": "sp500",
        "s&p500": "sp500",
        "s&p-style": "sp500",
        "nasdaq": "nasdaq",
        "nasdaq100": "nasdaq",
        "nasdaq-style": "nasdaq",
    }
    key = aliases.get(name.strip().lower())
    if key is None:
        raise ValueError("Universe name must be one of: sp500, s&p500, nasdaq, nasdaq100.")

    root = Path(base_path)
    candidates = [
        root / "universes" / f"{key}.csv",
        root / "universes" / f"{key}.txt",
        root / "data" / "universes" / f"{key}.csv",
        root / "data" / "universes" / f"{key}.txt",
    ]
    for candidate in candidates:
        if candidate.exists():
            return load_symbols_from_file(candidate)

    searched = ", ".join(str(path) for path in candidates)
    raise FileNotFoundError(f"No local {name} universe list found. Searched: {searched}")


def scan_results_to_dataframe(results: list[ScanResult]) -> pd.DataFrame:
    """Convert scan results to a DataFrame for easy viewing and CSV export.
    
    Args:
        results: List of ScanResult from scan_universe or similar
        
    Returns:
        pandas DataFrame with one row per result
    """
    rows = []
    for result in results:
        # Build timeframe signal strings
        weekly_result = result.timeframe_results.get("weekly", {})
        daily_result = result.timeframe_results.get("daily", {})
        hour4_result = result.timeframe_results.get("4hour", {})
        weekly_signals = ",".join(weekly_result.get("triggered_signals", [])) or "None"
        daily_signals = ",".join(daily_result.get("triggered_signals", [])) or "None"
        hour4_signals = ",".join(hour4_result.get("triggered_signals", [])) or "None"

        weekly_factors = ",".join(weekly_result.get("triggered_factors", [])) or "None"
        daily_factors = ",".join(daily_result.get("triggered_factors", [])) or "None"
        hour4_factors = ",".join(hour4_result.get("triggered_factors", [])) or "None"

        row = {
            "ticker": result.ticker,
            "total_score": result.total_score,
            "pre_multiplier_score": result.pre_multiplier_score,
            "cross_timeframe_all_factor_coverage_multiplier": result.cross_timeframe_all_factor_coverage_multiplier,
            "all_triggered_signals": ";".join(result.all_triggered_signals) or "None",
            "weekly_triggered_signals": weekly_signals,
            "weekly_triggered_factors": weekly_factors,
            "weekly_confluence_tier": weekly_result.get("factor_confluence_tier") or "None",
            "weekly_confluence_score": weekly_result.get("factor_confluence_score", 0),
            "daily_triggered_signals": daily_signals,
            "daily_triggered_factors": daily_factors,
            "daily_confluence_tier": daily_result.get("factor_confluence_tier") or "None",
            "daily_confluence_score": daily_result.get("factor_confluence_score", 0),
            "4hour_triggered_signals": hour4_signals,
            "4hour_triggered_factors": hour4_factors,
            "4hour_confluence_tier": hour4_result.get("factor_confluence_tier") or "None",
            "4hour_confluence_score": hour4_result.get("factor_confluence_score", 0),
            "data_source": result.data_source,
            "failed_reason": result.error or "None",
            "notes": "|".join(result.notes) if result.notes else "None",
        }
        rows.append(row)

    return pd.DataFrame(rows)
