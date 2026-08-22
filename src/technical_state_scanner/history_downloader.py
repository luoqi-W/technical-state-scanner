"""LongPort historical candlestick downloader.

This module uses LongPort's historical candlestick API to backfill and
incrementally update local OHLCV storage. Data is written to DuckDB for the
React API and mirrored to the parquet cache used by scanner code.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, time as dt_time, timedelta, timezone
from pathlib import Path
import sys
import time
from typing import Any

import pandas as pd

from technical_state_scanner.cache.cache_manager import load_cached, merge_new_bars, save_cache
from technical_state_scanner.db.duckdb_store import (
    get_connection,
    get_latest_timestamp,
    read_candles,
    upsert_candles,
)
from technical_state_scanner.loader import (
    _create_longport_quote_context,
    normalize_candles_to_ohlcv,
    normalize_symbol,
    resample_ohlcv,
)

DEFAULT_HISTORY_TIMEFRAMES = ["weekly", "daily", "4hour"]
HISTORY_BATCH_SIZE = 1000
RATE_LIMIT_INTERVAL_SECONDS = 0.55
SOURCE_PERIOD_TO_TIMEFRAME = {
    "1d": "daily",
    "1day": "daily",
    "day": "daily",
    "daily": "daily",
    "1w": "weekly",
    "week": "weekly",
    "weekly": "weekly",
    "4h": "4hour",
    "4hour": "4hour",
    "15m": "15min",
    "15min": "15min",
}


@dataclass
class HistoryDownloadResult:
    symbol: str
    timeframe: str
    started_at: datetime
    finished_at: datetime
    rows_written: int = 0
    pages_fetched: int = 0
    latest_timestamp: datetime | None = None
    error: str | None = None


@dataclass
class HistoryBatchResult:
    started_at: datetime
    finished_at: datetime
    symbols_processed: int
    timeframes: list[str]
    rows_written: int
    errors: list[str] = field(default_factory=list)
    results: list[HistoryDownloadResult] = field(default_factory=list)


class LongPortHistoryRateLimiter:
    """Simple process-local limiter for LongPort history API calls.

    The official limit is 60 requests per 30 seconds, so a minimum interval of
    0.55s keeps the downloader slightly under the ceiling.
    """

    def __init__(self, min_interval_seconds: float = RATE_LIMIT_INTERVAL_SECONDS):
        self.min_interval_seconds = min_interval_seconds
        self._last_call_at = 0.0

    def wait(self) -> None:
        elapsed = time.monotonic() - self._last_call_at
        remaining = self.min_interval_seconds - elapsed
        if remaining > 0:
            time.sleep(remaining)
        self._last_call_at = time.monotonic()


def _history_start_date(symbol: str, timeframe: str) -> date:
    suffix = normalize_symbol(symbol).split(".")[-1]
    if timeframe in {"4hour", "15min"}:
        if suffix == "HK":
            return date(2022, 9, 28)
        if suffix in {"SH", "SZ", "CN"}:
            return date(2022, 8, 25)
        return date(2023, 12, 4)
    if suffix == "HK":
        return date(2004, 6, 1)
    if suffix in {"SH", "SZ", "CN"}:
        return date(1999, 11, 1)
    return date(2010, 6, 1)


def _period_for_timeframe(timeframe: str) -> Any:
    from longport.openapi import Period

    if timeframe == "daily":
        return getattr(Period, "Day")
    if timeframe == "weekly":
        return getattr(Period, "Week")
    if timeframe == "4hour":
        if hasattr(Period, "Min_240"):
            return getattr(Period, "Min_240")
        raise RuntimeError("Installed LongPort SDK does not support Period.Min_240.")
    if timeframe == "15min":
        if hasattr(Period, "Min_15"):
            return getattr(Period, "Min_15")
        raise RuntimeError("Installed LongPort SDK does not support Period.Min_15.")
    raise ValueError(f"Unsupported history timeframe: {timeframe}")


def _adjust_type() -> Any:
    from longport.openapi import AdjustType

    return getattr(AdjustType, "ForwardAdjust", getattr(AdjustType, "NoAdjust"))


def _extract_candles(response: Any) -> list[Any]:
    if hasattr(response, "candlesticks"):
        return list(response.candlesticks)
    if isinstance(response, dict) and "candlesticks" in response:
        return list(response["candlesticks"])
    return list(response)


def _cursor_datetime(value: date | datetime) -> datetime:
    if isinstance(value, datetime):
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc)
    return datetime.combine(value, dt_time.min, tzinfo=timezone.utc)


def _call_history_by_offset(
    ctx: Any,
    symbol: str,
    timeframe: str,
    cursor: date | datetime,
    count: int = HISTORY_BATCH_SIZE,
) -> pd.DataFrame:
    method = getattr(ctx, "history_candlesticks_by_offset", None)
    if method is None:
        raise RuntimeError("Installed LongPort SDK does not expose history_candlesticks_by_offset().")

    period = _period_for_timeframe(timeframe)
    adjust_type = _adjust_type()
    cursor_dt = _cursor_datetime(cursor)

    try:
        response = method(symbol, period, adjust_type, True, count, cursor_dt)
    except TypeError:
        response = method(
            symbol=symbol,
            period=period,
            adjust_type=adjust_type,
            forward=True,
            count=count,
            date=cursor_dt,
        )
    candles = _extract_candles(response)
    if not candles:
        return pd.DataFrame(columns=["Open", "High", "Low", "Close", "Volume"])
    return normalize_candles_to_ohlcv(candles)


def _sync_parquet_cache(symbol: str, timeframe: str) -> None:
    frame = read_candles(symbol, timeframe)
    if frame.empty:
        return
    cached = load_cached(symbol, timeframe)
    if cached is not None and not cached.empty:
        frame = merge_new_bars(cached, frame)
    save_cache(frame, symbol, timeframe)


def _standardize_import_frame(frame: pd.DataFrame) -> pd.DataFrame:
    if "timestamp" in frame.columns:
        frame = frame.set_index("timestamp")
    elif "Datetime" in frame.columns:
        frame = frame.set_index("Datetime")

    rename_map = {
        "open": "Open",
        "high": "High",
        "low": "Low",
        "close": "Close",
        "volume": "Volume",
    }
    frame = frame.rename(columns=rename_map)
    required = ["Open", "High", "Low", "Close", "Volume"]
    missing = [column for column in required if column not in frame.columns]
    if missing:
        raise ValueError("Parquet file missing OHLCV columns: " + ", ".join(missing))

    out = frame[required].copy()
    out.index = pd.to_datetime(out.index, utc=True)
    out.index = pd.DatetimeIndex(out.index, tz="UTC")
    return out.sort_index()


def _source_timeframe_from_period_dir(period_dir: Path) -> str:
    name = period_dir.name
    period = name.split("=", 1)[1] if name.startswith("period=") else name
    key = period.strip().lower()
    if key not in SOURCE_PERIOD_TO_TIMEFRAME:
        raise ValueError(f"Unsupported source period directory: {period_dir}")
    return SOURCE_PERIOD_TO_TIMEFRAME[key]


def import_stockselection_parquet(
    source_root: str | Path,
    symbols: list[str] | None = None,
    timeframes: list[str] | None = None,
) -> HistoryBatchResult:
    """Import StockSelection-style partitioned parquet into local storage.

    Expected layout:
    ``data/parquet/period=4h/symbol=AAPL.US/data.parquet``.
    """

    root = Path(source_root)
    if not root.exists():
        raise FileNotFoundError(f"Source parquet root not found: {root}")

    started = datetime.now(timezone.utc)
    allowed_symbols = {normalize_symbol(symbol) for symbol in symbols} if symbols else None
    allowed_timeframes = set(timeframes) if timeframes else None
    results: list[HistoryDownloadResult] = []
    errors: list[str] = []
    total_rows = 0

    conn = get_connection()
    try:
        for period_dir in sorted(path for path in root.iterdir() if path.is_dir()):
            try:
                timeframe = _source_timeframe_from_period_dir(period_dir)
            except ValueError:
                continue
            if allowed_timeframes is not None and timeframe not in allowed_timeframes:
                continue

            for symbol_dir in sorted(path for path in period_dir.iterdir() if path.is_dir()):
                if not symbol_dir.name.startswith("symbol="):
                    continue
                symbol = normalize_symbol(symbol_dir.name.split("=", 1)[1])
                if allowed_symbols is not None and symbol not in allowed_symbols:
                    continue

                item_started = datetime.now(timezone.utc)
                item = HistoryDownloadResult(
                    symbol=symbol,
                    timeframe=timeframe,
                    started_at=item_started,
                    finished_at=item_started,
                )
                parquet_path = symbol_dir / "data.parquet"
                try:
                    frame = _standardize_import_frame(pd.read_parquet(parquet_path))
                    rows = upsert_candles(frame, symbol, timeframe, conn=conn)
                    save_cache(frame, symbol, timeframe)
                    item.rows_written = rows
                    item.pages_fetched = 0
                    item.latest_timestamp = frame.index.max().to_pydatetime() if not frame.empty else None
                    total_rows += rows
                except Exception as exc:
                    item.error = str(exc)
                    errors.append(f"{symbol}/{timeframe}: {exc}")
                finally:
                    item.finished_at = datetime.now(timezone.utc)
                    results.append(item)
    finally:
        conn.close()

    return HistoryBatchResult(
        started_at=started,
        finished_at=datetime.now(timezone.utc),
        symbols_processed=len({item.symbol for item in results}),
        timeframes=sorted({item.timeframe for item in results}),
        rows_written=total_rows,
        errors=errors,
        results=results,
    )


def download_history_for_symbol_timeframe(
    symbol: str,
    timeframe: str,
    ctx: Any | None = None,
    max_pages: int | None = None,
    rate_limiter: LongPortHistoryRateLimiter | None = None,
) -> HistoryDownloadResult:
    normalized = normalize_symbol(symbol)
    started = datetime.now(timezone.utc)
    result = HistoryDownloadResult(
        symbol=normalized,
        timeframe=timeframe,
        started_at=started,
        finished_at=started,
    )

    own_ctx = ctx is None
    if own_ctx:
        ctx = _create_longport_quote_context()
    limiter = rate_limiter or LongPortHistoryRateLimiter()

    conn = get_connection()
    try:
        latest = get_latest_timestamp(normalized, timeframe, conn=conn)
        cursor: date | datetime = latest if latest is not None else _history_start_date(normalized, timeframe)
        previous_max = latest

        while max_pages is None or result.pages_fetched < max_pages:
            limiter.wait()
            raw = _call_history_by_offset(ctx, normalized, timeframe, cursor, count=HISTORY_BATCH_SIZE)
            result.pages_fetched += 1
            if raw.empty:
                break

            if previous_max is not None:
                raw = raw[raw.index > pd.Timestamp(previous_max)]
            else:
                start_ts = pd.Timestamp(_history_start_date(normalized, timeframe), tz="UTC")
                raw = raw[raw.index >= start_ts]
            if raw.empty:
                break

            rows = upsert_candles(raw, normalized, timeframe, conn=conn)
            result.rows_written += rows
            max_ts = raw.index.max().to_pydatetime()
            result.latest_timestamp = max_ts
            if previous_max is not None and max_ts <= previous_max:
                break
            previous_max = max_ts
            cursor = max_ts + timedelta(seconds=1)
            if len(raw) < HISTORY_BATCH_SIZE:
                break

        if result.rows_written:
            _sync_parquet_cache(normalized, timeframe)
    except Exception as exc:
        result.error = str(exc)
    finally:
        conn.close()
        result.finished_at = datetime.now(timezone.utc)

    return result


def download_history_for_symbols(
    symbols: list[str],
    timeframes: list[str] | None = None,
    max_pages: int | None = None,
    on_progress: Any | None = None,
) -> HistoryBatchResult:
    selected_timeframes = timeframes or DEFAULT_HISTORY_TIMEFRAMES
    started = datetime.now(timezone.utc)
    ctx = _create_longport_quote_context()
    limiter = LongPortHistoryRateLimiter()
    results: list[HistoryDownloadResult] = []
    errors: list[str] = []

    for symbol in symbols:
        normalized = normalize_symbol(symbol)
        for timeframe in selected_timeframes:
            item = download_history_for_symbol_timeframe(
                normalized,
                timeframe,
                ctx=ctx,
                max_pages=max_pages,
                rate_limiter=limiter,
            )
            results.append(item)
            if item.error:
                errors.append(f"{normalized}/{timeframe}: {item.error}")
            if on_progress is not None:
                on_progress(item)

    return HistoryBatchResult(
        started_at=started,
        finished_at=datetime.now(timezone.utc),
        symbols_processed=len(symbols),
        timeframes=selected_timeframes,
        rows_written=sum(item.rows_written for item in results),
        errors=errors,
        results=results,
    )


def run_history_update_loop(
    symbols: list[str],
    timeframes: list[str] | None = None,
    interval_seconds: float = 24 * 3600,
    max_pages: int | None = 1,
) -> None:
    """Run a blocking incremental update loop."""

    while True:
        batch = download_history_for_symbols(symbols, timeframes=timeframes, max_pages=max_pages)
        print(
            f"[history] {batch.finished_at.isoformat()} updated "
            f"{batch.symbols_processed} symbols, rows={batch.rows_written}, errors={len(batch.errors)}",
            file=sys.stderr,
        )
        time.sleep(max(1.0, interval_seconds))


def run_daily_history_loop(
    symbols: list[str],
    timeframes: list[str] | None = None,
    interval_hours: float = 24.0,
    max_pages: int | None = 1,
) -> None:
    """Run a blocking daily incremental update loop."""

    run_history_update_loop(
        symbols=symbols,
        timeframes=timeframes,
        interval_seconds=interval_hours * 3600,
        max_pages=max_pages,
    )
