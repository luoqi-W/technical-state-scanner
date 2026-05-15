from __future__ import annotations

from datetime import datetime, timezone, timedelta

import pandas as pd

from technical_state_scanner.cache import cache_manager


def _frame(start: datetime | None = None, periods: int = 3) -> pd.DataFrame:
    start = start or datetime(2026, 1, 1, tzinfo=timezone.utc)
    return pd.DataFrame(
        {
            "Open": [10.0 + i for i in range(periods)],
            "High": [11.0 + i for i in range(periods)],
            "Low": [9.0 + i for i in range(periods)],
            "Close": [10.5 + i for i in range(periods)],
            "Volume": [1000.0 + i for i in range(periods)],
        },
        index=pd.date_range(start, periods=periods, freq="D", tz="UTC"),
    )


def _use_tmp_cache(monkeypatch, tmp_path):
    monkeypatch.setattr(cache_manager, "CACHE_ROOT", tmp_path / "data_cache")


def test_save_and_load_roundtrip(monkeypatch, tmp_path):
    """Save a DataFrame, load it, verify identical."""

    _use_tmp_cache(monkeypatch, tmp_path)
    frame = _frame()
    cache_manager.save_cache(frame, "AAPL.US", "daily")

    loaded = cache_manager.load_cached("AAPL.US", "daily")

    pd.testing.assert_frame_equal(loaded, frame, check_freq=False)


def test_load_nonexistent_returns_none(monkeypatch, tmp_path):
    """Loading a ticker that was never cached returns None."""

    _use_tmp_cache(monkeypatch, tmp_path)

    assert cache_manager.load_cached("AAPL.US", "daily") is None


def test_is_cache_fresh_true_for_recent_data(monkeypatch, tmp_path):
    """Cache with last bar 1 hour ago for 'daily' is fresh."""

    _use_tmp_cache(monkeypatch, tmp_path)
    frame = _frame(datetime.now(timezone.utc) - timedelta(hours=3), periods=3)
    cache_manager.save_cache(frame, "AAPL.US", "daily")

    assert cache_manager.is_cache_fresh("AAPL.US", "daily") is True


def test_is_cache_fresh_false_for_old_data(monkeypatch, tmp_path):
    """Cache with last bar 48 hours ago for 'daily' is stale."""

    _use_tmp_cache(monkeypatch, tmp_path)
    frame = _frame(datetime.now(timezone.utc) - timedelta(hours=96), periods=3)
    cache_manager.save_cache(frame, "AAPL.US", "daily")

    assert cache_manager.is_cache_fresh("AAPL.US", "daily") is False


def test_merge_new_bars_dedupes_overlaps():
    """When new bars overlap cached bars, new wins, no duplicate index."""

    cached = _frame(periods=3)
    new_bars = _frame(periods=4).iloc[2:].copy()
    new_bars.loc[new_bars.index[0], "Close"] = 99.0

    merged = cache_manager.merge_new_bars(cached, new_bars)

    assert len(merged) == 4
    assert merged.index.is_unique
    assert merged.loc[new_bars.index[0], "Close"] == 99.0


def test_clear_cache_specific_ticker(monkeypatch, tmp_path):
    """clear_cache('AAPL.US') removes all timeframes for that ticker."""

    _use_tmp_cache(monkeypatch, tmp_path)
    for timeframe in ["daily", "weekly", "4hour"]:
        cache_manager.save_cache(_frame(), "AAPL.US", timeframe)
    cache_manager.save_cache(_frame(), "MSFT.US", "daily")

    deleted = cache_manager.clear_cache("AAPL.US")

    assert deleted == 3
    assert cache_manager.load_cached("AAPL.US", "daily") is None
    assert cache_manager.load_cached("MSFT.US", "daily") is not None


def test_clear_cache_specific_timeframe(monkeypatch, tmp_path):
    """clear_cache('AAPL.US', 'daily') only removes the daily file."""

    _use_tmp_cache(monkeypatch, tmp_path)
    cache_manager.save_cache(_frame(), "AAPL.US", "daily")
    cache_manager.save_cache(_frame(), "AAPL.US", "weekly")

    deleted = cache_manager.clear_cache("AAPL.US", "daily")

    assert deleted == 1
    assert cache_manager.load_cached("AAPL.US", "daily") is None
    assert cache_manager.load_cached("AAPL.US", "weekly") is not None
