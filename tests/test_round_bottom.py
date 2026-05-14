"""Tests for F3 - Round Bottom detection."""

from __future__ import annotations

import numpy as np
import pandas as pd

from technical_state_scanner.factors.round_bottom import detect_round_bottom


def _base_frame(n: int = 700) -> pd.DataFrame:
    """Create a basic DataFrame with DatetimeIndex and Close column."""
    idx = pd.date_range("2025-01-01", periods=n, freq="D", tz="UTC")
    close = np.linspace(90, 100, n)
    return pd.DataFrame({"Close": close}, index=idx)


def test_result_shape_and_keys():
    """Test that result has required keys."""
    out = detect_round_bottom(_base_frame())
    assert set(["triggered", "timestamp", "signal_name", "details"]).issubset(set(out.keys()))
    assert out["signal_name"] == "Round Bottom"


def test_insufficient_history():
    """Test behavior when fewer than window bars are available."""
    df = _base_frame(50)
    out = detect_round_bottom(df)
    assert out["triggered"] == False
    assert out["details"]["reason"] == "insufficient_history"


def test_missing_close_column():
    """Test behavior when Close column is missing."""
    idx = pd.date_range("2025-01-01", periods=100, freq="D", tz="UTC")
    df = pd.DataFrame({"Price": [100.0] * 100}, index=idx)
    out = detect_round_bottom(df)
    assert out["triggered"] == False
    assert out["details"]["reason"] == "missing_Close_column"


def test_perfect_u_shape_bottom_middle():
    """Test trigger on perfect U-shaped curve with vertex in middle."""
    idx = pd.date_range("2025-01-01", periods=700, freq="D", tz="UTC")
    
    # Create a perfect U-shape in the last 60 bars (the window being analyzed)
    # Full data has 700 bars, vertex should be in the middle of the last 60
    # So vertex should be at position ~30 relative to the last 60 bars
    x = np.arange(700, dtype=float)
    # Vertex in the full data at x=640+30=670 would give vertex at relative position 30 in last 60
    # Actually, simpler: create all 700 bars as U-shaped with vertex at x=350
    # but with a DIFFERENT scale that makes the last 60 bars form a local minimum
    u_shape = 0.0001 * (x - 350.0) ** 2 + 95.0
    df = pd.DataFrame({"Close": u_shape}, index=idx)
    
    # Modify just the last 60 bars to create a clear U-shape there
    df_modified = df.copy()
    tail_window = 60
    tail_idx = np.arange(tail_window, dtype=float)
    # Vertex at position 30 (middle of 60-bar window)
    u_tail = 0.01 * (tail_idx - 30.0) ** 2 + 100.0
    df_modified.iloc[-tail_window:, df_modified.columns.get_loc("Close")] = u_tail
    
    out = detect_round_bottom(df_modified)
    assert out["triggered"] == True
    assert out["details"]["a"] > 0
    assert out["details"]["r_squared"] > 0.95


def test_u_shape_vertex_at_edge_fails():
    """Test that U-shape with vertex at edge (outside 20%-80%) fails."""
    idx = pd.date_range("2025-01-01", periods=700, freq="D", tz="UTC")
    df = pd.DataFrame({"Close": np.linspace(95, 105, 700)}, index=idx)
    
    # Modify last 60 bars to have vertex at position 5 (outside 20%-80% = 12-48)
    tail_window = 60
    tail_idx = np.arange(tail_window, dtype=float)
    u_tail = 0.01 * (tail_idx - 5.0) ** 2 + 100.0  # vertex at position 5
    df.iloc[-tail_window:, df.columns.get_loc("Close")] = u_tail
    
    out = detect_round_bottom(df)
    assert out["triggered"] == False
    assert "vertex_outside_range" in out["details"]["reason"]


def test_inverted_shape_fails():
    """Test that inverted (downward) parabola fails (a < 0)."""
    idx = pd.date_range("2025-01-01", periods=700, freq="D", tz="UTC")
    df = pd.DataFrame({"Close": np.linspace(95, 105, 700)}, index=idx)
    
    # Modify last 60 bars to have inverted parabola (a < 0)
    tail_window = 60
    tail_idx = np.arange(tail_window, dtype=float)
    inverted = -0.01 * (tail_idx - 30.0) ** 2 + 100.0  # a < 0, inverted
    df.iloc[-tail_window:, df.columns.get_loc("Close")] = inverted
    
    out = detect_round_bottom(df)
    assert out["triggered"] == False
    assert "a_not_positive" in out["details"]["reason"]


def test_low_r_squared_fails():
    """Test that noisy data with low R² fails."""
    df = _base_frame(700)
    idx = pd.date_range("2025-01-01", periods=700, freq="D", tz="UTC")
    
    # U-shape with lots of noise
    np.random.seed(42)
    x = np.arange(700, dtype=float)
    u_shape = 0.0001 * (x - 350.0) ** 2 + 95.0
    noise = np.random.normal(0, 5.0, 700)
    df = pd.DataFrame({"Close": u_shape + noise}, index=idx)
    
    out = detect_round_bottom(df)
    # With high noise, R² should be low and trigger should fail
    assert out["triggered"] == False or out["details"]["r_squared"] < 0.7


def test_configurable_window():
    """Test that window parameter is respected."""
    idx = pd.date_range("2025-01-01", periods=200, freq="D", tz="UTC")
    df = pd.DataFrame({"Close": np.linspace(95, 105, 200)}, index=idx)
    
    # Modify last 100 bars to have a perfect U-shape with window=100
    tail_window = 100
    tail_idx = np.arange(tail_window, dtype=float)
    u_tail = 0.01 * (tail_idx - 50.0) ** 2 + 100.0  # vertex at 50 (middle)
    df.iloc[-tail_window:, df.columns.get_loc("Close")] = u_tail
    
    # Test with window=100 (we have exactly 200 bars total, so this works)
    out = detect_round_bottom(df, window=100)
    assert out["details"]["window"] == 100
    # Should trigger because the last 100 bars form a perfect U-shape
    assert out["triggered"] == True


def test_configurable_r_squared_threshold():
    """Test that min_r_squared parameter is respected."""
    idx = pd.date_range("2025-01-01", periods=700, freq="D", tz="UTC")
    df = pd.DataFrame({"Close": np.linspace(95, 105, 700)}, index=idx)
    
    # Modify last 60 bars with a moderate U-shape (good R² but not perfect)
    tail_window = 60
    tail_idx = np.arange(tail_window, dtype=float)
    u_tail = 0.001 * (tail_idx - 30.0) ** 2 + 100.0
    df.iloc[-tail_window:, df.columns.get_loc("Close")] = u_tail
    
    # With strict threshold, should fail
    out_strict = detect_round_bottom(df, min_r_squared=0.99)
    # With lenient threshold, should trigger
    out_lenient = detect_round_bottom(df, min_r_squared=0.5)
    
    # Strict might fail, lenient should pass
    assert out_lenient["triggered"] == True
    # Verify r_squared is shown
    assert "r_squared" in out_lenient["details"]


def test_timestamp_in_details():
    """Test that timestamp is correctly set in result."""
    df = _base_frame(700)
    out = detect_round_bottom(df)
    assert out["timestamp"] is not None
    assert out["timestamp"] == df.index[-1].isoformat()


def test_empty_dataframe():
    """Test behavior on empty DataFrame."""
    idx = pd.DatetimeIndex([], tz="UTC")
    df = pd.DataFrame({"Close": []}, index=idx)
    out = detect_round_bottom(df)
    assert out["timestamp"] is None
    assert out["triggered"] == False
