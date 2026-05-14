"""Tests for F5 - Big Bullish Candle detection."""

from __future__ import annotations

import numpy as np
import pandas as pd

from technical_state_scanner.factors.big_candle import detect_big_bullish_candle


def _base_frame(n: int = 100) -> pd.DataFrame:
    """Create a basic DataFrame with all required columns."""
    idx = pd.date_range("2025-01-01", periods=n, freq="D", tz="UTC")
    return pd.DataFrame(
        {
            "Open": np.full(n, 100.0),
            "Close": np.full(n, 100.0),
            "EMA12": np.full(n, 99.5),
            "EMA144": np.full(n, 99.0),
            "EMA169": np.full(n, 99.0),
        },
        index=idx,
    )


def test_result_shape_and_keys():
    """Test that result has required keys."""
    out = detect_big_bullish_candle(_base_frame())
    assert set(["triggered", "timestamp", "signal_name", "details"]).issubset(set(out.keys()))
    assert out["signal_name"] == "Big Bullish Candle"


def test_insufficient_history():
    """Test behavior when fewer than 20 bars are available."""
    df = _base_frame(10)
    out = detect_big_bullish_candle(df)
    assert out["triggered"] == False
    assert out["details"]["reason"] == "insufficient_history"


def test_missing_columns():
    """Test behavior when required columns are missing."""
    idx = pd.date_range("2025-01-01", periods=100, freq="D", tz="UTC")
    df = pd.DataFrame(
        {
            "Open": np.full(100, 100.0),
            "Close": np.full(100, 101.0),
        },
        index=idx,
    )
    out = detect_big_bullish_candle(df)
    assert out["triggered"] == False
    assert "missing_columns" in out["details"]["reason"]


def test_big_bullish_trigger_all_conditions():
    """Test that a proper big bullish candle triggers."""
    df = _base_frame(100)
    
    # Set previous 20 bars to have small bodies (~0.3 each)
    df.iloc[-21:-1, df.columns.get_loc("Open")] = np.full(20, 100.0)
    df.iloc[-21:-1, df.columns.get_loc("Close")] = np.full(20, 100.3)
    
    # Set current candle to be large bullish
    # Open=100, Close=103 -> body=3, gain=3%
    df.iloc[-1, df.columns.get_loc("Open")] = 100.0
    df.iloc[-1, df.columns.get_loc("Close")] = 103.0
    
    # Set EMAs below the close
    df.iloc[-1, df.columns.get_loc("EMA12")] = 99.0
    df.iloc[-1, df.columns.get_loc("EMA144")] = 98.5
    df.iloc[-1, df.columns.get_loc("EMA169")] = 98.5
    
    out = detect_big_bullish_candle(df)
    assert out["triggered"] == True
    assert out["details"]["gain_pct"] > 0.025
    assert out["details"]["body_ratio"] > 1.5
    assert out["details"]["distance_above_emas_pct"] > 0


def test_bearish_candle_fails():
    """Test that a bearish candle (close < open) fails."""
    df = _base_frame(100)
    
    # Bearish candle: open > close
    df.iloc[-1, df.columns.get_loc("Open")] = 105.0
    df.iloc[-1, df.columns.get_loc("Close")] = 100.0
    df.iloc[-1, df.columns.get_loc("EMA12")] = 99.0
    
    out = detect_big_bullish_candle(df)
    assert out["triggered"] == False
    assert "not_bullish" in out["details"]["reason"]


def test_insufficient_body_size_fails():
    """Test that a candle with small body fails."""
    df = _base_frame(100)
    
    # Small body: only 0.5%
    df.iloc[-1, df.columns.get_loc("Open")] = 100.0
    df.iloc[-1, df.columns.get_loc("Close")] = 100.5
    df.iloc[-1, df.columns.get_loc("EMA12")] = 99.0
    
    out = detect_big_bullish_candle(df)
    assert out["triggered"] == False
    assert "insufficient_body_size" in out["details"]["reason"]


def test_body_not_outsized_fails():
    """Test that a candle with normal-sized body (no 1.5x ratio) fails."""
    df = _base_frame(100)
    
    # Previous 20 bars have average body of 1.0
    df.iloc[-21:-1, df.columns.get_loc("Open")] = np.full(20, 100.0)
    df.iloc[-21:-1, df.columns.get_loc("Close")] = np.full(20, 101.0)
    
    # Current candle has body of 1.1 (not 1.5x of 1.0)
    df.iloc[-1, df.columns.get_loc("Open")] = 100.0
    df.iloc[-1, df.columns.get_loc("Close")] = 101.1
    df.iloc[-1, df.columns.get_loc("EMA12")] = 99.0
    
    out = detect_big_bullish_candle(df)
    assert out["triggered"] == False
    assert "body_not_outsized" in out["details"]["reason"]


def test_not_above_emas_fails():
    """Test that close not clearly above EMAs fails."""
    df = _base_frame(100)
    
    # Set previous 20 bars to have small bodies
    df.iloc[-21:-1, df.columns.get_loc("Open")] = np.full(20, 100.0)
    df.iloc[-21:-1, df.columns.get_loc("Close")] = np.full(20, 100.3)
    
    # Current candle has good body but close is only at EMA level
    df.iloc[-1, df.columns.get_loc("Open")] = 100.0
    df.iloc[-1, df.columns.get_loc("Close")] = 103.0
    # EMAs at 102.5 - not enough clearance
    df.iloc[-1, df.columns.get_loc("EMA12")] = 102.5
    df.iloc[-1, df.columns.get_loc("EMA144")] = 102.0
    df.iloc[-1, df.columns.get_loc("EMA169")] = 102.0
    
    out = detect_big_bullish_candle(df)
    assert out["triggered"] == False
    assert "not_above_emas" in out["details"]["reason"]


def test_configurable_min_body_pct():
    """Test that min_body_pct parameter is respected."""
    df = _base_frame(100)
    
    # Previous 20 bars with small bodies
    df.iloc[-21:-1, df.columns.get_loc("Open")] = np.full(20, 100.0)
    df.iloc[-21:-1, df.columns.get_loc("Close")] = np.full(20, 100.3)
    
    # Current candle with 1.5% body
    df.iloc[-1, df.columns.get_loc("Open")] = 100.0
    df.iloc[-1, df.columns.get_loc("Close")] = 101.5
    df.iloc[-1, df.columns.get_loc("EMA12")] = 99.0
    
    # With strict threshold (3%), should fail
    out_strict = detect_big_bullish_candle(df, min_body_pct=0.03)
    assert out_strict["triggered"] == False
    
    # With lenient threshold (1%), should consider other conditions
    out_lenient = detect_big_bullish_candle(df, min_body_pct=0.01)
    # May pass or fail based on body_ratio condition


def test_configurable_body_ratio_threshold():
    """Test that body_ratio_threshold parameter is respected."""
    df = _base_frame(100)
    
    # Previous 20 bars: average body = 1.0
    df.iloc[-21:-1, df.columns.get_loc("Open")] = np.full(20, 100.0)
    df.iloc[-21:-1, df.columns.get_loc("Close")] = np.full(20, 101.0)
    
    # Current candle: body = 3.0 (gain = 3%, meets min_body_pct of 2.5%)
    # ratio = 3.0 / 1.0 = 3.0
    df.iloc[-1, df.columns.get_loc("Open")] = 100.0
    df.iloc[-1, df.columns.get_loc("Close")] = 103.0
    df.iloc[-1, df.columns.get_loc("EMA12")] = 99.0
    df.iloc[-1, df.columns.get_loc("EMA144")] = 99.0
    df.iloc[-1, df.columns.get_loc("EMA169")] = 99.0
    
    # With strict threshold (4.0), should fail
    out_strict = detect_big_bullish_candle(df, body_ratio_threshold=4.0)
    assert out_strict["triggered"] == False
    
    # With lenient threshold (2.0), should trigger
    out_lenient = detect_big_bullish_candle(df, body_ratio_threshold=2.0)
    assert out_lenient["triggered"] == True


def test_configurable_ema_clearance_pct():
    """Test that ema_clearance_pct parameter is respected."""
    df = _base_frame(100)
    
    # Previous 20 bars with small bodies
    df.iloc[-21:-1, df.columns.get_loc("Open")] = np.full(20, 100.0)
    df.iloc[-21:-1, df.columns.get_loc("Close")] = np.full(20, 100.3)
    
    # Current candle: body = 3.0
    df.iloc[-1, df.columns.get_loc("Open")] = 100.0
    df.iloc[-1, df.columns.get_loc("Close")] = 103.0
    # EMAs at 101.5
    df.iloc[-1, df.columns.get_loc("EMA12")] = 101.5
    df.iloc[-1, df.columns.get_loc("EMA144")] = 101.5
    df.iloc[-1, df.columns.get_loc("EMA169")] = 101.5
    
    # With strict clearance (3%), 101.5 * 1.03 = 104.545 > 103, should fail
    out_strict = detect_big_bullish_candle(df, ema_clearance_pct=0.03)
    assert out_strict["triggered"] == False
    
    # With lenient clearance (0.5%), 101.5 * 1.005 = 102.01 < 103, should trigger
    out_lenient = detect_big_bullish_candle(df, ema_clearance_pct=0.005)
    assert out_lenient["triggered"] == True


def test_timestamp_in_details():
    """Test that timestamp is correctly set in result."""
    df = _base_frame(100)
    out = detect_big_bullish_candle(df)
    assert out["timestamp"] is not None
    assert out["timestamp"] == df.index[-1].isoformat()


def test_empty_dataframe():
    """Test behavior on empty DataFrame."""
    idx = pd.DatetimeIndex([], tz="UTC")
    df = pd.DataFrame(
        {
            "Open": [],
            "Close": [],
            "EMA12": [],
            "EMA144": [],
            "EMA169": [],
        },
        index=idx,
    )
    out = detect_big_bullish_candle(df)
    assert out["timestamp"] is None
    assert out["triggered"] == False
