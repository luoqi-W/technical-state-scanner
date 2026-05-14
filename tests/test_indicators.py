from __future__ import annotations

import pandas as pd

from technical_state_scanner.core.indicators import add_ema_columns, add_vegas_tunnel_columns


def _frame(n: int) -> pd.DataFrame:
    idx = pd.date_range("2026-01-01", periods=n, freq="D", tz="UTC")
    close = pd.Series(range(1, n + 1), index=idx, dtype=float)
    return pd.DataFrame(
        {
            "Open": close,
            "High": close + 1,
            "Low": close - 1,
            "Close": close,
            "Volume": 1000.0,
        },
        index=idx,
    )


def test_add_ema_columns_creates_required_columns():
    frame = _frame(700)
    out, status = add_ema_columns(frame)
    for col in ["EMA12", "EMA144", "EMA169", "EMA576", "EMA676"]:
        assert col in out.columns
    assert status.ok is True
    assert status.insufficient_history is False


def test_insufficient_history_status_when_under_676_bars():
    frame = _frame(200)
    out, status = add_vegas_tunnel_columns(frame)
    assert "VegasLower" in out.columns
    assert "VegasUpper" in out.columns
    assert status.ok is False
    assert status.insufficient_history is True
    assert status.reason is not None
    assert "insufficient_history" in status.reason
