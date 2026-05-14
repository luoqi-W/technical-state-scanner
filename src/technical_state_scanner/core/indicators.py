from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

EMA_PERIODS = [12, 144, 169, 576, 676]
EMA_COLUMNS = [f"EMA{period}" for period in EMA_PERIODS]


@dataclass(frozen=True)
class IndicatorStatus:
    ok: bool
    insufficient_history: bool
    reason: str | None = None


def add_ema_columns(frame: pd.DataFrame) -> tuple[pd.DataFrame, IndicatorStatus]:
    out = frame.copy()
    for period in EMA_PERIODS:
        out[f"EMA{period}"] = out["Close"].ewm(span=period, adjust=False).mean()

    if len(out) < 676:
        return out, IndicatorStatus(
            ok=False,
            insufficient_history=True,
            reason=f"insufficient_history: requires >=676 bars, got {len(out)}",
        )

    return out, IndicatorStatus(ok=True, insufficient_history=False)


def add_vegas_tunnel_columns(frame: pd.DataFrame) -> tuple[pd.DataFrame, IndicatorStatus]:
    out, status = add_ema_columns(frame)
    # Vegas tunnel is defined by EMA144 and EMA169 in this project.
    out["VegasLower"] = out[["EMA144", "EMA169"]].min(axis=1)
    out["VegasUpper"] = out[["EMA144", "EMA169"]].max(axis=1)
    return out, status
