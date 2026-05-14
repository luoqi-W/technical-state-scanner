"""Tests for independent signal aggregation."""

from __future__ import annotations

import numpy as np
import pandas as pd

from technical_state_scanner.core.signal_aggregator import aggregate_signals
from technical_state_scanner.factors.ema12_liftoff import detect_ema12_liftoff
from technical_state_scanner.factors.round_bottom import detect_round_bottom
from technical_state_scanner.factors.triangle import detect_triangle_consolidation
from technical_state_scanner.factors.vegas_alignment import detect_vegas_alignment
from technical_state_scanner.factors.big_candle import detect_big_bullish_candle
from technical_state_scanner.factors.volume_surge import detect_volume_surge


def _triangle_volume_frame() -> pd.DataFrame:
    idx = pd.date_range("2025-01-01", periods=30, freq="D", tz="UTC")
    x = np.arange(30, dtype=float)
    highs = 110.0 - 0.55 * x
    lows = 90.0 + 0.55 * x
    peak_positions = np.arange(3, 27, 5)
    trough_positions = np.arange(5, 27, 5)
    highs[peak_positions] += 4.0
    lows[trough_positions] -= 4.0
    volume = np.concatenate([np.full(29, 100.0), [800.0]])
    return pd.DataFrame({"High": highs, "Low": lows, "Volume": volume}, index=idx)


def _empty_frame() -> pd.DataFrame:
    return pd.DataFrame(index=pd.DatetimeIndex([], tz="UTC"))


def test_multiple_factors_triggering_at_same_time():
    df = _triangle_volume_frame()
    out = aggregate_signals(df)

    assert set(out["triggered_factors"]) == {"F4", "F6"}
    assert out["triggered_signals"] == ["Triangle Consolidation", "Volume Surge"]
    assert out["details"]["F4"]["triggered"] is True
    assert out["details"]["F6"]["triggered"] is True


def test_no_factors_triggering():
    df = _empty_frame()
    out = aggregate_signals(df)

    assert out["triggered_signals"] == []
    assert out["triggered_factors"] == []
    assert all(not out["details"][factor]["triggered"] for factor in out["details"])


def test_all_factor_details_preserved():
    df = _empty_frame()
    out = aggregate_signals(df)

    expected = {
        "F1": detect_vegas_alignment(df),
        "F2": detect_ema12_liftoff(df),
        "F3": detect_round_bottom(df),
        "F4": detect_triangle_consolidation(df),
        "F5": detect_big_bullish_candle(df),
        "F6": detect_volume_surge(df),
    }
    assert out["details"] == expected


def test_no_primary_state_or_display_state_in_output():
    df = _empty_frame()
    out = aggregate_signals(df)

    assert "primary_state" not in out
    assert "display_state" not in out
    assert "priority" not in out


def test_no_factor_priority_applied():
    df = _triangle_volume_frame()
    out = aggregate_signals(df)

    assert list(out.keys()) == ["triggered_signals", "triggered_factors", "details"]
    assert "priority" not in out
    assert "priority" not in out["details"]
