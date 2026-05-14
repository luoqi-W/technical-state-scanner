from __future__ import annotations

import pandas as pd

from technical_state_scanner.factors.vegas_alignment import detect_vegas_alignment


def _base_frame(n: int = 700) -> pd.DataFrame:
    idx = pd.date_range("2025-01-01", periods=n, freq="D", tz="UTC")
    return pd.DataFrame({"Close": [100.0] * n, "EMA12": [100.0] * n, "EMA144": [99.8] * n, "EMA169": [100.2] * n, "EMA576": [99.9] * n, "EMA676": [100.1] * n}, index=idx)


def test_result_shape_and_keys():
    out = detect_vegas_alignment(_base_frame())
    assert set(["triggered", "timestamp", "signal_name", "details"]).issubset(set(out.keys()))
    assert out["signal_name"] == "F1_VEGAS_ALIGNMENT"


def test_positions_and_insufficient_history():
    out = detect_vegas_alignment(_base_frame(200))
    assert out["triggered"] is False
    assert out["details"]["reason"] == "insufficient_history"
