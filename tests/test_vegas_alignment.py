from __future__ import annotations

import pandas as pd

from technical_state_scanner.factors.vegas_alignment import detect_vegas_alignment


def _base_frame(n: int = 700) -> pd.DataFrame:
    idx = pd.date_range("2025-01-01", periods=n, freq="D", tz="UTC")
    return pd.DataFrame(
        {
            "Close": [100.0] * n,
            "EMA12": [100.0] * n,
            "EMA144": [99.8] * n,
            "EMA169": [100.2] * n,
            "EMA576": [99.9] * n,
            "EMA676": [100.1] * n,
        },
        index=idx,
    )


def test_overlapping_tunnels_mode_a():
    df = _base_frame()
    df.iloc[-1, df.columns.get_loc("EMA144")] = 98.0
    df.iloc[-1, df.columns.get_loc("EMA169")] = 102.0
    df.iloc[-1, df.columns.get_loc("EMA576")] = 100.0
    df.iloc[-1, df.columns.get_loc("EMA676")] = 104.0
    out = detect_vegas_alignment(df, compression_threshold_pct=0.1, close_parallel_threshold_pct=0.01)
    assert out["mode"] == "A"


def test_close_parallel_tunnels_mode_b():
    df = _base_frame()
    df.iloc[-1, df.columns.get_loc("EMA144")] = 100.0
    df.iloc[-1, df.columns.get_loc("EMA169")] = 100.2
    df.iloc[-1, df.columns.get_loc("EMA576")] = 100.3
    df.iloc[-1, df.columns.get_loc("EMA676")] = 100.5
    out = detect_vegas_alignment(df, compression_threshold_pct=0.1, close_parallel_threshold_pct=0.5)
    assert out["mode"] == "B"


def test_tight_compression_mode_c():
    df = _base_frame()
    out = detect_vegas_alignment(df, compression_threshold_pct=1.5)
    assert out["mode"] in ["C", "D"]


def test_ema12_inside():
    df = _base_frame()
    df.iloc[-1, df.columns.get_loc("EMA12")] = 100.0
    out = detect_vegas_alignment(df)
    assert out["ema12_position"] == "INSIDE_TUNNEL"


def test_ema12_slightly_above():
    df = _base_frame()
    df.iloc[-1, df.columns.get_loc("EMA12")] = 100.5
    out = detect_vegas_alignment(df)
    assert out["ema12_position"] == "ABOVE_TUNNEL"


def test_ema12_below():
    df = _base_frame()
    df.iloc[-1, df.columns.get_loc("EMA12")] = 99.0
    out = detect_vegas_alignment(df)
    assert out["ema12_position"] == "BELOW_TUNNEL"


def test_insufficient_history():
    df = _base_frame(200)
    out = detect_vegas_alignment(df)
    assert out["triggered"] is False
    assert out["reason"] == "insufficient_history"
