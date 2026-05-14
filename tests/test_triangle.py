"""Tests for F4 - Triangle Consolidation detection."""

from __future__ import annotations

import numpy as np
import pandas as pd

from technical_state_scanner.factors.triangle import detect_triangle_consolidation


def _triangle_frame(
    window: int = 30,
    slope_high: float = -0.2,
    slope_low: float = 0.2,
    peak_offset: float = 4.0,
    trough_offset: float = 4.0,
) -> pd.DataFrame:
    idx = pd.date_range("2025-01-01", periods=window, freq="D", tz="UTC")
    x = np.arange(window, dtype=float)
    highs = 110.0 + slope_high * x
    lows = 90.0 + slope_low * x

    peak_positions = np.arange(3, window - 3, 5)
    trough_positions = np.arange(5, window - 3, 5)
    highs[peak_positions] += peak_offset
    lows[trough_positions] -= trough_offset

    return pd.DataFrame({"High": highs, "Low": lows}, index=idx)


def _base_frame(n: int = 100) -> pd.DataFrame:
    idx = pd.date_range("2025-01-01", periods=n, freq="D", tz="UTC")
    return pd.DataFrame({"High": np.linspace(100, 110, n), "Low": np.linspace(90, 100, n)}, index=idx)


def test_result_shape_and_keys():
    out = detect_triangle_consolidation(_triangle_frame())
    assert set(["triggered", "timestamp", "signal_name", "details"]).issubset(set(out.keys()))
    assert out["signal_name"] == "Triangle Consolidation"


def test_symmetrical_triangle_triggers():
    df = _triangle_frame(slope_high=-0.3, slope_low=0.3)
    out = detect_triangle_consolidation(df)
    assert out["triggered"] is True
    assert out["details"]["type"] == "Symmetrical"
    assert out["details"]["contraction_ratio"] < 0.6


def test_ascending_triangle_triggers():
    df = _triangle_frame(slope_high=0.0, slope_low=0.55)
    out = detect_triangle_consolidation(df)
    assert out["triggered"] is True
    assert out["details"]["type"] == "Ascending"
    assert abs(out["details"]["slope_high"]) < 0.01
    assert out["details"]["slope_low"] > 0


def test_descending_triangle_triggers():
    df = _triangle_frame(slope_high=-0.55, slope_low=0.0)
    out = detect_triangle_consolidation(df)
    assert out["triggered"] is True
    assert out["details"]["type"] == "Descending"
    assert out["details"]["slope_high"] < 0
    assert abs(out["details"]["slope_low"]) < 0.01


def test_failed_contraction_does_not_trigger():
    df = _triangle_frame(slope_high=-0.05, slope_low=0.05)
    out = detect_triangle_consolidation(df)
    assert out["triggered"] is False
    assert out["details"]["reason"] == "contraction_ratio_too_large"


def test_insufficient_history():
    df = _base_frame(20)
    out = detect_triangle_consolidation(df)
    assert out["triggered"] is False
    assert out["details"]["reason"] == "insufficient_history"


def test_missing_columns():
    idx = pd.date_range("2025-01-01", periods=40, freq="D", tz="UTC")
    df = pd.DataFrame({"Price": np.linspace(100, 105, 40)}, index=idx)
    out = detect_triangle_consolidation(df)
    assert out["triggered"] is False
    assert "missing_columns" in out["details"]["reason"]


def test_not_enough_pivots():
    idx = pd.date_range("2025-01-01", periods=40, freq="D", tz="UTC")
    highs = np.linspace(100, 100, 40)
    lows = np.linspace(90, 90, 40)
    df = pd.DataFrame({"High": highs, "Low": lows}, index=idx)
    out = detect_triangle_consolidation(df)
    assert out["triggered"] is False
    assert out["details"]["reason"] == "not_enough_pivots"


def test_timestamp_and_output_values():
    df = _triangle_frame()
    out = detect_triangle_consolidation(df)
    assert out["timestamp"] == df.index[-1].isoformat()
    assert out["details"]["num_high_pivots"] >= 2
    assert out["details"]["num_low_pivots"] >= 2
    assert isinstance(out["details"]["contraction_ratio"], float)
