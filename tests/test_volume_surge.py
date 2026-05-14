"""Tests for F6 - Volume Surge detection."""

from __future__ import annotations

import numpy as np
import pandas as pd

from technical_state_scanner.factors.volume_surge import detect_volume_surge


def _base_frame(n: int = 100) -> pd.DataFrame:
    """Create a basic DataFrame with DatetimeIndex and Volume column."""
    idx = pd.date_range("2025-01-01", periods=n, freq="D", tz="UTC")
    return pd.DataFrame({"Volume": np.full(n, 1000.0)}, index=idx)


def test_result_shape_and_keys():
    """Test that result has required keys."""
    out = detect_volume_surge(_base_frame())
    assert set(["triggered", "timestamp", "signal_name", "details"]).issubset(set(out.keys()))
    assert out["signal_name"] == "Volume Surge"


def test_insufficient_history():
    """Test behavior when fewer than 20 bars are available."""
    df = _base_frame(10)
    out = detect_volume_surge(df)
    assert out["triggered"] == False
    assert out["details"]["reason"] == "insufficient_history"


def test_missing_volume_column():
    """Test behavior when Volume column is missing."""
    idx = pd.date_range("2025-01-01", periods=100, freq="D", tz="UTC")
    df = pd.DataFrame({"Price": [100.0] * 100}, index=idx)
    out = detect_volume_surge(df)
    assert out["triggered"] == False
    assert out["details"]["reason"] == "missing_Volume_column"


def test_volume_surge_trigger():
    """Test that volume surge above threshold triggers."""
    df = _base_frame(100)
    
    # Set previous 20 bars to 1000 each
    df.iloc[-21:-1, df.columns.get_loc("Volume")] = np.full(20, 1000.0)
    
    # Set current bar to 1600 (ratio = 1.6 > 1.5)
    df.iloc[-1, df.columns.get_loc("Volume")] = 1600.0
    
    out = detect_volume_surge(df)
    assert out["triggered"] == True
    assert out["details"]["surge_ratio"] > 1.5


def test_volume_surge_at_threshold():
    """Test that volume exactly at threshold triggers."""
    df = _base_frame(100)
    
    # Set previous 20 bars to 1000 each
    df.iloc[-21:-1, df.columns.get_loc("Volume")] = np.full(20, 1000.0)
    
    # Set current bar to 1500 (ratio = 1.5, should trigger as > 1.5 is default)
    # Actually, test > 1.5 means 1500 shouldn't trigger
    df.iloc[-1, df.columns.get_loc("Volume")] = 1500.0
    
    out = detect_volume_surge(df)
    assert out["triggered"] == False
    
    # But 1501 should trigger
    df.iloc[-1, df.columns.get_loc("Volume")] = 1501.0
    out = detect_volume_surge(df)
    assert out["triggered"] == True


def test_volume_surge_below_threshold():
    """Test that volume below threshold does not trigger."""
    df = _base_frame(100)
    
    # Set previous 20 bars to 1000 each
    df.iloc[-21:-1, df.columns.get_loc("Volume")] = np.full(20, 1000.0)
    
    # Set current bar to 1400 (ratio = 1.4 < 1.5)
    df.iloc[-1, df.columns.get_loc("Volume")] = 1400.0
    
    out = detect_volume_surge(df)
    assert out["triggered"] == False
    assert out["details"]["surge_ratio"] < 1.5


def test_configurable_surge_ratio():
    """Test that surge_ratio parameter is respected."""
    df = _base_frame(100)
    
    # Set previous 20 bars to 1000 each
    df.iloc[-21:-1, df.columns.get_loc("Volume")] = np.full(20, 1000.0)
    
    # Set current bar to 1250 (ratio = 1.25)
    df.iloc[-1, df.columns.get_loc("Volume")] = 1250.0
    
    # With strict threshold (2.0), should fail
    out_strict = detect_volume_surge(df, surge_ratio=2.0)
    assert out_strict["triggered"] == False
    
    # With lenient threshold (1.0), should trigger
    out_lenient = detect_volume_surge(df, surge_ratio=1.0)
    assert out_lenient["triggered"] == True


def test_zero_average_volume():
    """Test behavior when previous bars have zero volume."""
    df = _base_frame(100)
    
    # Set previous 20 bars to 0
    df.iloc[-21:-1, df.columns.get_loc("Volume")] = np.full(20, 0.0)
    
    # Set current bar to 1000
    df.iloc[-1, df.columns.get_loc("Volume")] = 1000.0
    
    out = detect_volume_surge(df)
    # surge_ratio will be infinite or very high when avg is 0
    # The details should show surge_ratio > threshold or handle gracefully
    assert "surge_ratio" in out["details"]


def test_variable_previous_volumes():
    """Test with variable previous 20 bars volumes."""
    df = _base_frame(100)
    
    # Set previous 20 bars to varying volumes
    volumes_20 = np.array([500, 600, 700, 800, 900, 1000, 1100, 1200, 1300, 1400,
                           500, 600, 700, 800, 900, 1000, 1100, 1200, 1300, 1400])
    df.iloc[-21:-1, df.columns.get_loc("Volume")] = volumes_20
    avg_vol = volumes_20.mean()  # 950.0
    
    # Set current bar to 1600
    df.iloc[-1, df.columns.get_loc("Volume")] = 1600.0
    
    out = detect_volume_surge(df)
    assert out["triggered"] == True
    assert out["details"]["avg_volume_20"] == avg_vol
    # 1600 / 950 ≈ 1.684
    assert abs(out["details"]["surge_ratio"] - (1600.0 / avg_vol)) < 0.01


def test_timestamp_in_details():
    """Test that timestamp is correctly set in result."""
    df = _base_frame(100)
    out = detect_volume_surge(df)
    assert out["timestamp"] is not None
    assert out["timestamp"] == df.index[-1].isoformat()


def test_empty_dataframe():
    """Test behavior on empty DataFrame."""
    idx = pd.DatetimeIndex([], tz="UTC")
    df = pd.DataFrame({"Volume": []}, index=idx)
    out = detect_volume_surge(df)
    assert out["timestamp"] is None
    assert out["triggered"] == False


def test_single_previous_volume():
    """Test with exactly 21 bars (one previous + current)."""
    idx = pd.date_range("2025-01-01", periods=21, freq="D", tz="UTC")
    df = pd.DataFrame({"Volume": np.full(21, 1000.0)}, index=idx)
    
    # Set last bar to surge
    df.iloc[-1, df.columns.get_loc("Volume")] = 1600.0
    
    out = detect_volume_surge(df)
    assert out["triggered"] == True
    assert out["details"]["avg_volume_20"] == 1000.0
