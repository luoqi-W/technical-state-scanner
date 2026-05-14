from __future__ import annotations

import numpy as np
import pandas as pd

REQUIRED_COLUMNS = ["EMA12", "EMA144", "EMA169", "EMA576", "EMA676", "Close"]


def _result(ts: str | None, triggered: bool, details: dict) -> dict:
    return {
        "triggered": triggered,
        "timestamp": ts,
        "signal_name": "F2_EMA12_LIFTOFF",
        "details": details,
    }


def _vegas_bounds(df: pd.DataFrame) -> tuple[pd.Series, pd.Series]:
    lower = pd.concat([df["EMA144"], df["EMA169"], df["EMA576"], df["EMA676"]], axis=1).min(axis=1)
    upper = pd.concat([df["EMA144"], df["EMA169"], df["EMA576"], df["EMA676"]], axis=1).max(axis=1)
    return lower, upper


def detect_ema12_liftoff(df: pd.DataFrame, **params) -> dict:
    ts = df.index[-1].isoformat() if len(df) > 0 else None
    if len(df) < 676:
        return _result(ts, False, {"reason": "insufficient_history"})
    missing = [c for c in REQUIRED_COLUMNS if c not in df.columns]
    if missing:
        return _result(ts, False, {"reason": f"missing_columns: {', '.join(missing)}"})

    attachment_lookback = int(params.get("attachment_lookback", 10))
    attached_distance_pct = float(params.get("attached_distance_pct", 0.005))
    curvature_window = int(params.get("curvature_window", 5))
    distance_compare_bars = int(params.get("distance_compare_bars", 3))

    lower, upper = _vegas_bounds(df)
    ema12 = df["EMA12"]
    close = df["Close"]

    pct_dist_to_range = np.where(
        ema12 > upper,
        (ema12 - upper) / close,
        np.where(ema12 < lower, (lower - ema12) / close, 0.0),
    )
    pct_dist_series = pd.Series(pct_dist_to_range, index=df.index)

    recent_dist = pct_dist_series.tail(attachment_lookback)
    was_attached_recently = bool((recent_dist <= attached_distance_pct).any())

    if len(df) < curvature_window:
        return _result(ts, False, {"reason": "insufficient_curvature_window"})

    y = ema12.tail(curvature_window).to_numpy(dtype=float)
    x = np.arange(len(y), dtype=float)
    a, b, c = np.polyfit(x, y, 2)
    y_hat = a * (x**2) + b * x + c
    ss_res = float(np.sum((y - y_hat) ** 2))
    ss_tot = float(np.sum((y - np.mean(y)) ** 2))
    r_squared = 1.0 - (ss_res / ss_tot) if ss_tot != 0 else 1.0

    current_upper = float(upper.iloc[-1])
    current_ema12 = float(ema12.iloc[-1])
    is_above_tunnel = current_ema12 > current_upper

    if len(pct_dist_series) <= distance_compare_bars:
        distance_increasing = False
    else:
        distance_increasing = float(pct_dist_series.iloc[-1]) > float(pct_dist_series.iloc[-1 - distance_compare_bars])

    current_slope = float(ema12.iloc[-1] - ema12.iloc[-2]) if len(ema12) >= 2 else 0.0
    distance_pct = float(pct_dist_series.iloc[-1])

    conditions = {
        "was_attached_recently": was_attached_recently,
        "positive_curvature": a > 0,
        "is_above_tunnel": is_above_tunnel,
        "distance_increasing": distance_increasing,
    }
    triggered = all(conditions.values())

    details = {
        "curvature_a": float(a),
        "current_slope": current_slope,
        "r_squared": float(r_squared),
        "distance_pct": distance_pct,
        "was_attached_recently": was_attached_recently,
        "distance_increasing": distance_increasing,
    }

    if not triggered:
        failed = [k for k, v in conditions.items() if not v]
        details["reason"] = "conditions_failed: " + ",".join(failed)

    return _result(ts, triggered, details)
