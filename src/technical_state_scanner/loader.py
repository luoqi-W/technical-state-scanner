"""LongPort candlestick data loading and normalization utilities."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal
import inspect
import sys
from typing import Any
import warnings

import pandas as pd

from technical_state_scanner.config import ENV_VAR_GROUPS, get_longport_env_value, get_missing_longport_env_groups
from technical_state_scanner.cache.cache_manager import (
    load_cached,
    merge_new_bars,
    save_cache,
    is_cache_fresh,
)
from technical_state_scanner.core.indicators import IndicatorStatus, add_vegas_tunnel_columns

OHLCV_COLUMNS = ["Open", "High", "Low", "Close", "Volume"]
TIMEFRAME_TO_PERIOD_NAME = {"daily": "Day", "weekly": "Week", "4hour": "Min_240", "15min": "Min_15"}
SMART_INCREMENTAL_FETCH_COUNT = 30


@dataclass(frozen=True)
class LongPortCredentials:
    app_key: str
    app_secret: str
    access_token: str


def normalize_symbol(symbol: str) -> str:
    text = symbol.strip().upper()
    if not text:
        raise ValueError("Symbol cannot be empty.")
    if "." in text:
        return text
    return f"{text}.US"


def load_longport_credentials_from_env() -> LongPortCredentials:
    missing = get_missing_longport_env_groups()
    if missing:
        raise RuntimeError("Missing required LongPort environment variables: " + ", ".join(missing))
    app_key = get_longport_env_value(*ENV_VAR_GROUPS[0])
    app_secret = get_longport_env_value(*ENV_VAR_GROUPS[1])
    access_token = get_longport_env_value(*ENV_VAR_GROUPS[2])
    return LongPortCredentials(
        app_key=app_key or "",
        app_secret=app_secret or "",
        access_token=access_token or "",
    )


def _create_longport_config(config_class: Any, creds: LongPortCredentials) -> Any:
    """Create a LongPort config across legacy and current SDK versions."""

    from_apikey = getattr(config_class, "from_apikey", None)
    if callable(from_apikey):
        return from_apikey(creds.app_key, creds.app_secret, creds.access_token)
    return config_class(creds.app_key, creds.app_secret, creds.access_token)


def _to_float(value: Any) -> float:
    return float(value if not isinstance(value, Decimal) else float(value))


def normalize_candles_to_ohlcv(candles: Sequence[Any]) -> pd.DataFrame:
    if not candles:
        raise RuntimeError("LongPort returned empty candlestick data.")
    rows: list[dict[str, Any]] = []
    for candle in candles:
        timestamp = getattr(candle, "timestamp", None)
        if timestamp is None:
            raise RuntimeError("LongPort candle is missing required `timestamp` field.")
        if isinstance(timestamp, (int, float)):
            parsed_timestamp = pd.to_datetime(timestamp, unit="s", utc=True)
        else:
            parsed_timestamp = pd.to_datetime(timestamp, utc=True)
        rows.append({
            "Datetime": parsed_timestamp,
            "Open": _to_float(getattr(candle, "open")),
            "High": _to_float(getattr(candle, "high")),
            "Low": _to_float(getattr(candle, "low")),
            "Close": _to_float(getattr(candle, "close")),
            "Volume": _to_float(getattr(candle, "volume")),
        })
    frame = pd.DataFrame(rows).set_index("Datetime").sort_index()
    frame.index = pd.DatetimeIndex(frame.index, tz="UTC")
    return frame[OHLCV_COLUMNS]


def _get_window_start(timestamp: pd.Timestamp, freq: str) -> pd.Timestamp:
    try:
        return timestamp.floor(freq)
    except ValueError:
        naive_timestamp = timestamp.tz_localize(None)
        period_start = naive_timestamp.to_period(freq).start_time
        start = pd.Timestamp(period_start)
        if start.tzinfo is None:
            start = start.tz_localize(timestamp.tz)
        return start


def _drop_incomplete_last_bar(frame: pd.DataFrame, freq: str, now_utc: datetime | None = None) -> pd.DataFrame:
    if frame.empty:
        return frame
    now = now_utc or datetime.now(timezone.utc)
    last_ts = frame.index.max()
    start = _get_window_start(last_ts, freq)
    offset = pd.tseries.frequencies.to_offset(freq)
    if now < (start + offset):
        return frame.iloc[:-1]
    return frame


def resample_ohlcv(frame: pd.DataFrame, freq: str, now_utc: datetime | None = None) -> pd.DataFrame:
    resampled = frame.resample(freq, label="left", closed="left").agg(
        {"Open": "first", "High": "max", "Low": "min", "Close": "last", "Volume": "sum"}
    ).dropna(subset=["Open", "High", "Low", "Close"])
    return _drop_incomplete_last_bar(resampled, freq=freq, now_utc=now_utc)


def _get_supported_trade_sessions() -> Any | None:
    try:
        from longport.openapi import TradeSessions
    except Exception:  # pragma: no cover - depends on installed SDK version
        return None
    return getattr(TradeSessions, "All", None)


def _get_callable_parameters(func: Any) -> dict[str, inspect.Parameter]:
    try:
        return dict(inspect.signature(func).parameters)
    except (TypeError, ValueError):  # pragma: no cover - defensive for native SDK callables
        return {}


def _safe_signature_text(func: Any) -> str:
    try:
        return str(inspect.signature(func))
    except (TypeError, ValueError):  # pragma: no cover - defensive for native SDK callables
        return "unavailable"


def _log_longport_loader_event(message: str) -> None:
    print(f"[LongPort loader] {message}", file=sys.stderr)


def _call_candlesticks_with_signature(
    ctx: Any,
    symbol: str,
    period_value: Any,
    count: int,
    adjust_type: Any,
    trade_sessions: Any | None,
) -> tuple[Sequence[Any], str]:
    params = _get_callable_parameters(ctx.candlesticks)
    has_count = "count" in params
    has_adjust_type = "adjust_type" in params
    has_trade_sessions = "trade_sessions" in params or "trade_session" in params

    if has_count:
        kwargs: dict[str, Any] = {
            "symbol": symbol,
            "period": period_value,
            "count": count,
        }
        if has_adjust_type:
            kwargs["adjust_type"] = adjust_type
        else:
            warnings.warn(
                "Installed LongPort SDK candlesticks() does not expose adjust_type; using closest compatible call.",
                RuntimeWarning,
                stacklevel=2,
            )
        if has_trade_sessions and trade_sessions is not None:
            session_param = "trade_sessions" if "trade_sessions" in params else "trade_session"
            kwargs[session_param] = trade_sessions
        elif trade_sessions is not None:
            warnings.warn(
                "Installed LongPort SDK candlesticks() does not expose trade_sessions; using closest compatible call.",
                RuntimeWarning,
                stacklevel=2,
            )

        try:
            return ctx.candlesticks(**kwargs), "keyword"
        except TypeError:
            if has_adjust_type and has_trade_sessions and trade_sessions is not None:
                return ctx.candlesticks(symbol, period_value, count, adjust_type, trade_sessions), "positional_fallback_with_trade_sessions"
            if has_adjust_type:
                return ctx.candlesticks(symbol, period_value, count, adjust_type), "positional_fallback"
            return ctx.candlesticks(symbol, period_value, count), "positional_fallback_without_adjust_type"

    warnings.warn(
        "Installed LongPort SDK candlesticks() signature does not expose count; attempting legacy compatible call.",
        RuntimeWarning,
        stacklevel=2,
    )
    if has_adjust_type:
        return ctx.candlesticks(symbol=symbol, period=period_value, adjust_type=adjust_type), "legacy_keyword_without_count"
    return ctx.candlesticks(symbol, period_value), "legacy_positional_without_count"


def _load_candles_raw(ctx: Any, period_value: Any, symbol: str, count: int, timeframe: str | None = None) -> pd.DataFrame:
    from longport.openapi import AdjustType

    if not isinstance(count, int):
        raise TypeError(f"LongPort candlestick count must be an integer, got {type(count).__name__}.")

    trade_sessions = _get_supported_trade_sessions()
    signature_text = _safe_signature_text(ctx.candlesticks)
    _log_longport_loader_event(
        "candlesticks signature="
        f"{signature_text}; timeframe={timeframe or 'unknown'}; symbol={symbol}; "
        f"count={count}; count_type={type(count).__name__}; count_is_int={isinstance(count, int)}; "
        "adjust_type_target=adjust_type; adjust_type_in_count=False; "
        f"trade_sessions_requested={trade_sessions is not None}"
    )
    candles, call_path = _call_candlesticks_with_signature(
        ctx=ctx,
        symbol=symbol,
        period_value=period_value,
        count=count,
        adjust_type=AdjustType.ForwardAdjust,
        trade_sessions=trade_sessions,
    )
    candle_count = len(candles) if hasattr(candles, "__len__") else "unknown"
    _log_longport_loader_event(
        f"candlesticks call_path={call_path}; timeframe={timeframe or 'unknown'}; "
        f"returned_candles={candle_count}"
    )
    frame = normalize_candles_to_ohlcv(candles)
    _log_longport_loader_event(
        f"OHLCV timeframe={timeframe or 'unknown'}; rows={len(frame)}; "
        f"non_empty={not frame.empty}; columns={list(frame.columns)}"
    )
    return frame


def load_multi_timeframe_ohlcv(symbol: str, count: int = 300) -> tuple[dict[str, pd.DataFrame], dict[str, IndicatorStatus]]:
    try:
        from longport.openapi import Config, Period, QuoteContext
    except Exception as exc:  # pragma: no cover
        raise RuntimeError("LongPort SDK is not installed or importable. Install dependency `longport`.") from exc

    creds = load_longport_credentials_from_env()
    normalized_symbol = normalize_symbol(symbol)
    ctx = QuoteContext(_create_longport_config(Config, creds))

    frames: dict[str, pd.DataFrame] = {}

    daily = _load_candles_raw(ctx, getattr(Period, "Day"), normalized_symbol, count=count, timeframe="daily")
    frames["daily"] = daily.tail(count)

    if hasattr(Period, "Week"):
        weekly = _load_candles_raw(ctx, getattr(Period, "Week"), normalized_symbol, count=count, timeframe="weekly")
    else:
        weekly = resample_ohlcv(daily, "W-MON")
    frames["weekly"] = weekly.tail(count)

    if hasattr(Period, "Min_240"):
        h4 = _load_candles_raw(ctx, getattr(Period, "Min_240"), normalized_symbol, count=count, timeframe="4hour")
    else:
        # fallback from lower timeframe data if Min_240 is unavailable
        if hasattr(Period, "Min_60"):
            h1 = _load_candles_raw(ctx, getattr(Period, "Min_60"), normalized_symbol, count=count, timeframe="1hour")
            h4 = resample_ohlcv(h1, "4h")
        else:
            raise RuntimeError("LongPort SDK does not support Period.Min_240 or Period.Min_60 for fallback resampling.")
    frames["4hour"] = h4.tail(count)

    statuses: dict[str, IndicatorStatus] = {}
    for timeframe in ["weekly", "daily", "4hour"]:
        if frames[timeframe].empty:
            raise RuntimeError(f"LongPort returned empty candlestick data for timeframe: {timeframe}.")
        frames[timeframe], statuses[timeframe] = add_vegas_tunnel_columns(frames[timeframe])
    return frames, statuses


def _create_longport_quote_context() -> Any:
    try:
        from longport.openapi import Config, QuoteContext
    except Exception as exc:  # pragma: no cover
        raise RuntimeError("LongPort SDK is not installed or importable. Install dependency `longport`.") from exc

    creds = load_longport_credentials_from_env()
    return QuoteContext(_create_longport_config(Config, creds))


def _fetch_timeframe_ohlcv(ctx: Any, symbol: str, timeframe: str, count: int) -> pd.DataFrame:
    from longport.openapi import Period

    if timeframe == "daily":
        return _load_candles_raw(ctx, getattr(Period, "Day"), symbol, count=count, timeframe="daily")
    if timeframe == "weekly":
        if hasattr(Period, "Week"):
            return _load_candles_raw(ctx, getattr(Period, "Week"), symbol, count=count, timeframe="weekly")
        daily_count = max(count * 7, count)
        daily = _load_candles_raw(ctx, getattr(Period, "Day"), symbol, count=daily_count, timeframe="daily")
        return resample_ohlcv(daily, "W-MON")
    if timeframe == "4hour":
        if hasattr(Period, "Min_240"):
            return _load_candles_raw(ctx, getattr(Period, "Min_240"), symbol, count=count, timeframe="4hour")
        if hasattr(Period, "Min_60"):
            h1 = _load_candles_raw(ctx, getattr(Period, "Min_60"), symbol, count=max(count * 4, count), timeframe="1hour")
            return resample_ohlcv(h1, "4h")
        raise RuntimeError("LongPort SDK does not support Period.Min_240 or Period.Min_60 for fallback resampling.")
    if timeframe == "15min":
        if hasattr(Period, "Min_15"):
            return _load_candles_raw(ctx, getattr(Period, "Min_15"), symbol, count=count, timeframe="15min")
        raise RuntimeError("LongPort SDK does not support Period.Min_15.")
    raise ValueError(f"Unsupported timeframe: {timeframe}")


def _load_ohlcv_smart_raw(
    symbol: str,
    timeframe: str,
    count: int = 700,
    force_refresh: bool = False,
) -> pd.DataFrame:
    normalized_symbol = normalize_symbol(symbol)
    cached = None if force_refresh else load_cached(normalized_symbol, timeframe)

    if force_refresh or cached is None:
        ctx = _create_longport_quote_context()
        fetched = _fetch_timeframe_ohlcv(ctx, normalized_symbol, timeframe, count)
        save_cache(fetched, normalized_symbol, timeframe)
        return fetched.tail(count)

    if is_cache_fresh(normalized_symbol, timeframe):
        return cached.tail(count)

    try:
        ctx = _create_longport_quote_context()
        # LongPort candlesticks does not expose a stable fetch-since timestamp API in
        # the supported SDK versions. Fetch a small recent window, then merge by
        # timestamp so overlapping bars are updated and genuinely new bars are added.
        recent = _fetch_timeframe_ohlcv(ctx, normalized_symbol, timeframe, SMART_INCREMENTAL_FETCH_COUNT)
        merged = merge_new_bars(cached, recent)
        save_cache(merged, normalized_symbol, timeframe)
        return merged.tail(count)
    except Exception as exc:
        _log_longport_loader_event(
            f"incremental refresh failed; using stale cache; "
            f"timeframe={timeframe}; symbol={normalized_symbol}; error={exc}"
        )
        return cached.tail(count)


def load_ohlcv_smart(
    symbol: str,
    timeframe: str,
    count: int = 700,
    force_refresh: bool = False,
) -> pd.DataFrame:
    """Cache-first loader with incremental updates."""

    frame = _load_ohlcv_smart_raw(
        symbol=symbol,
        timeframe=timeframe,
        count=count,
        force_refresh=force_refresh,
    )
    if frame.empty:
        raise RuntimeError(f"LongPort returned empty candlestick data for timeframe: {timeframe}.")
    frame, _status = add_vegas_tunnel_columns(frame)
    return frame.tail(count)


def load_multi_timeframe_ohlcv_smart(
    symbol: str,
    count: int = 700,
    force_refresh: bool = False,
) -> tuple[dict[str, pd.DataFrame], dict[str, IndicatorStatus]]:
    """Load weekly, daily, and 4-hour OHLCV through the local parquet cache."""

    normalized_symbol = normalize_symbol(symbol)
    frames: dict[str, pd.DataFrame] = {}
    statuses: dict[str, IndicatorStatus] = {}
    for timeframe in ["weekly", "daily", "4hour"]:
        raw = _load_ohlcv_smart_raw(
            symbol=normalized_symbol,
            timeframe=timeframe,
            count=count,
            force_refresh=force_refresh,
        )
        if raw.empty:
            raise RuntimeError(f"LongPort returned empty candlestick data for timeframe: {timeframe}.")
        frames[timeframe], statuses[timeframe] = add_vegas_tunnel_columns(raw.tail(count))
    return frames, statuses
