from __future__ import annotations

import numpy as np
import pandas as pd

from technical_state_scanner.factors.ema12_liftoff import detect_ema12_liftoff


def _frame(n: int = 700) -> pd.DataFrame:
    idx = pd.date_range("2025-01-01", periods=n, freq="D", tz="UTC")
    base = np.linspace(90, 100, n)
    return pd.DataFrame(
        {
            "Close": np.full(n, 100.0),
            "EMA144": base,
            "EMA169": base + 0.1,
            "EMA576": base - 0.1,
            "EMA676": base,
            "EMA12": base,
        },
        index=idx,
    )


def test_successful_liftoff():
    df = _frame()
    df.iloc[-10:, df.columns.get_loc("EMA12")] = [99.9, 100.0, 100.0, 100.02, 100.05, 100.1, 100.2, 100.35, 100.6, 101.0]
    out = detect_ema12_liftoff(df)
    assert out["triggered"] is True


def test_no_recent_attachment():
    df = _frame()
    df["EMA12"] = df["EMA12"] + 5.0
    out = detect_ema12_liftoff(df)
    assert out["triggered"] is False


def test_negative_curvature():
    df = _frame()
    df.iloc[-5:, df.columns.get_loc("EMA12")] = [101.2, 101.1, 101.0, 100.9, 100.8]
    out = detect_ema12_liftoff(df)
    assert out["triggered"] is False


def test_not_above_tunnel():
    df = _frame()
    df.iloc[-10:, df.columns.get_loc("EMA12")] = [99.8, 99.9, 100, 100.01, 100.02, 100.03, 100.04, 100.05, 100.06, 100.07]
    out = detect_ema12_liftoff(df)
    assert out["triggered"] is False


def test_distance_not_increasing():
    df = _frame()
    df.iloc[-10:, df.columns.get_loc("EMA12")] = [99.9, 100.0, 100.2, 100.4, 100.7, 101.0, 101.0, 100.95, 100.9, 100.85]
    out = detect_ema12_liftoff(df)
    assert out["triggered"] is False


def test_insufficient_history():
    out = detect_ema12_liftoff(_frame(200))
    assert out["triggered"] is False
    assert out["details"]["reason"] == "insufficient_history"
