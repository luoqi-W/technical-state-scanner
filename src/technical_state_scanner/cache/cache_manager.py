from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import pandas as pd


CACHE_ROOT = Path("data_cache")
CACHE_FRESHNESS_HOURS = {
    "daily": 12,
    "4hour": 2,
    "weekly": 72,
}
OHLCV_COLUMNS = ["Open", "High", "Low", "Close", "Volume"]


def _safe_symbol(symbol: str) -> str:
    return symbol.strip().upper().replace("/", "_").replace("\\", "_")


def _normalize_index(frame: pd.DataFrame) -> pd.DataFrame:
    out = frame.copy()
    out.index = pd.to_datetime(out.index, utc=True)
    out.index = pd.DatetimeIndex(out.index, tz="UTC")
    return out.sort_index()


def _validate_timeframe(timeframe: str) -> None:
    if timeframe not in CACHE_FRESHNESS_HOURS:
        raise ValueError(f"Unsupported cache timeframe: {timeframe}")


def _validate_ohlcv_frame(df: pd.DataFrame) -> None:
    if not isinstance(df.index, pd.DatetimeIndex):
        raise ValueError("Cache DataFrame index must be a DatetimeIndex.")
    if df.index.tz is None:
        raise ValueError("Cache DataFrame index must be timezone-aware.")
    missing = [column for column in OHLCV_COLUMNS if column not in df.columns]
    if missing:
        raise ValueError("Cache DataFrame missing OHLCV columns: " + ", ".join(missing))


def get_cache_path(symbol: str, timeframe: str) -> Path:
    """Return Path to the parquet file for this ticker+timeframe."""

    _validate_timeframe(timeframe)
    return CACHE_ROOT / timeframe / f"{_safe_symbol(symbol)}.parquet"


def load_cached(symbol: str, timeframe: str) -> pd.DataFrame | None:
    """Read from cache, returning None if missing or unreadable."""

    path = get_cache_path(symbol, timeframe)
    if not path.exists():
        return None
    try:
        frame = pd.read_parquet(path)
        frame = _normalize_index(frame)
        _validate_ohlcv_frame(frame)
        return frame[OHLCV_COLUMNS]
    except Exception:
        return None


def save_cache(df: pd.DataFrame, symbol: str, timeframe: str) -> None:
    """Write OHLCV DataFrame to cache."""

    _validate_timeframe(timeframe)
    frame = _normalize_index(df)
    _validate_ohlcv_frame(frame)
    path = get_cache_path(symbol, timeframe)
    path.parent.mkdir(parents=True, exist_ok=True)
    frame[OHLCV_COLUMNS].to_parquet(path)


def get_cache_metadata(symbol: str, timeframe: str) -> dict | None:
    """Return basic cache metadata or None if unavailable."""

    path = get_cache_path(symbol, timeframe)
    frame = load_cached(symbol, timeframe)
    if frame is None or frame.empty or not path.exists():
        return None
    return {
        "last_bar_time": frame.index.max(),
        "bar_count": int(len(frame)),
        "file_size_kb": int(max(1, path.stat().st_size // 1024)),
    }


def is_cache_fresh(symbol: str, timeframe: str) -> bool:
    """Return True when the latest cached bar is within the freshness window."""

    metadata = get_cache_metadata(symbol, timeframe)
    if metadata is None:
        return False
    last_bar_time = metadata["last_bar_time"]
    if last_bar_time.tzinfo is None:
        last_bar_time = last_bar_time.tz_localize(timezone.utc)
    age_hours = (datetime.now(timezone.utc) - last_bar_time.to_pydatetime()).total_seconds() / 3600
    return age_hours <= CACHE_FRESHNESS_HOURS[timeframe]


def merge_new_bars(cached: pd.DataFrame, new_bars: pd.DataFrame) -> pd.DataFrame:
    """Merge new bars into cached data, keeping new rows on index conflicts."""

    cached_frame = _normalize_index(cached)
    new_frame = _normalize_index(new_bars)
    _validate_ohlcv_frame(cached_frame)
    _validate_ohlcv_frame(new_frame)
    merged = pd.concat([cached_frame, new_frame])
    merged = merged[~merged.index.duplicated(keep="last")]
    return merged.sort_index()[OHLCV_COLUMNS]


def clear_cache(symbol: str | None = None, timeframe: str | None = None) -> int:
    """Clear cache entries and return the number of files deleted."""

    if timeframe is not None:
        _validate_timeframe(timeframe)
    if not CACHE_ROOT.exists():
        return 0

    if symbol is None and timeframe is None:
        candidates = list(CACHE_ROOT.glob("*/*.parquet"))
    elif symbol is None:
        candidates = list((CACHE_ROOT / timeframe).glob("*.parquet"))
    elif timeframe is None:
        safe = _safe_symbol(symbol)
        candidates = list(CACHE_ROOT.glob(f"*/{safe}.parquet"))
    else:
        candidates = [get_cache_path(symbol, timeframe)]

    deleted = 0
    for path in candidates:
        if path.exists() and path.is_file():
            path.unlink()
            deleted += 1
    return deleted
