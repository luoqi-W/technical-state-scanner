"""LongPort candlestick data loading and normalization utilities."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from decimal import Decimal
import os
from typing import Any

import pandas as pd

from technical_state_scanner.config import REQUIRED_ENV_VARS
from technical_state_scanner.core.indicators import IndicatorStatus, add_vegas_tunnel_columns

OHLCV_COLUMNS = ["Open", "High", "Low", "Close", "Volume"]
TIMEFRAME_TO_PERIOD_NAME = {"daily": "Day", "weekly": "Week", "4hour": "Min_240"}


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
    missing = [name for name in REQUIRED_ENV_VARS if not os.getenv(name)]
    if missing:
        raise RuntimeError("Missing required LongPort environment variables: " + ", ".join(missing))
    return LongPortCredentials(
        app_key=os.environ["LONGPORT_APP_KEY"],
        app_secret=os.environ["LONGPORT_APP_SECRET"],
        access_token=os.environ["LONGPORT_ACCESS_TOKEN"],
    )


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
        rows.append({
            "Datetime": pd.to_datetime(timestamp, utc=True),
            "Open": _to_float(getattr(candle, "open")),
            "High": _to_float(getattr(candle, "high")),
            "Low": _to_float(getattr(candle, "low")),
            "Close": _to_float(getattr(candle, "close")),
            "Volume": _to_float(getattr(candle, "volume")),
        })
    frame = pd.DataFrame(rows).set_index("Datetime").sort_index()
    frame.index = pd.DatetimeIndex(frame.index, tz="UTC")
    return frame[OHLCV_COLUMNS]


def _drop_incomplete_last_bar(frame: pd.DataFrame, freq: str, now_utc: datetime | None = None) -> pd.DataFrame:
    if frame.empty:
        return frame
    now = now_utc or datetime.now(timezone.utc)
    last_ts = frame.index.max()
    start = last_ts.floor(freq)
    if now < (start + pd.Timedelta(freq)):
        return frame.iloc[:-1]
    return frame


def resample_ohlcv(frame: pd.DataFrame, freq: str, now_utc: datetime | None = None) -> pd.DataFrame:
    resampled = frame.resample(freq, label="left", closed="left").agg(
        {"Open": "first", "High": "max", "Low": "min", "Close": "last", "Volume": "sum"}
    ).dropna(subset=["Open", "High", "Low", "Close"])
    return _drop_incomplete_last_bar(resampled, freq=freq, now_utc=now_utc)


def _load_candles_raw(ctx: Any, period_value: Any, symbol: str, start_at: datetime, end_at: datetime) -> pd.DataFrame:
    from longport.openapi import AdjustType
    candles = ctx.candlesticks(symbol, period_value, AdjustType.ForwardAdjust, start_at, end_at)
    return normalize_candles_to_ohlcv(candles)


def load_multi_timeframe_ohlcv(symbol: str, count: int = 300) -> tuple[dict[str, pd.DataFrame], dict[str, IndicatorStatus]]:
    try:
        from longport.openapi import Config, Period, QuoteContext
    except Exception as exc:  # pragma: no cover
        raise RuntimeError("LongPort SDK is not installed or importable. Install dependency `longport`.") from exc

    creds = load_longport_credentials_from_env()
    normalized_symbol = normalize_symbol(symbol)
    ctx = QuoteContext(Config(creds.app_key, creds.app_secret, creds.access_token))

    end_at = datetime.now(timezone.utc)
    start_at = end_at - timedelta(days=1200)

    frames: dict[str, pd.DataFrame] = {}

    daily = _load_candles_raw(ctx, getattr(Period, "Day"), normalized_symbol, start_at, end_at)
    frames["daily"] = daily.tail(count)

    if hasattr(Period, "Week"):
        weekly = _load_candles_raw(ctx, getattr(Period, "Week"), normalized_symbol, start_at, end_at)
    else:
        weekly = resample_ohlcv(daily, "W-MON")
    frames["weekly"] = weekly.tail(count)

    if hasattr(Period, "Min_240"):
        h4 = _load_candles_raw(ctx, getattr(Period, "Min_240"), normalized_symbol, start_at, end_at)
    else:
        # fallback from lower timeframe data if Min_240 is unavailable
        if hasattr(Period, "Min_60"):
            h1 = _load_candles_raw(ctx, getattr(Period, "Min_60"), normalized_symbol, start_at, end_at)
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
