"""F4 - Triangle Consolidation detection."""

from __future__ import annotations

import numpy as np
import pandas as pd


def _result(ts: str | None, triggered: bool, details: dict) -> dict:
    return {
        "triggered": triggered,
        "timestamp": ts,
        "signal_name": "Triangle Consolidation",
        "details": details,
    }


def _find_local_pivots(highs: np.ndarray, lows: np.ndarray, pivot: int) -> tuple[list[int], list[int]]:
    high_pivots: list[int] = []
    low_pivots: list[int] = []
    n = len(highs)
    for i in range(pivot, n - pivot):
        center_high = highs[i]
        window_high = np.concatenate((highs[i - pivot : i], highs[i + 1 : i + pivot + 1]))
        if np.all(center_high > window_high):
            high_pivots.append(i)

        center_low = lows[i]
        window_low = np.concatenate((lows[i - pivot : i], lows[i + 1 : i + pivot + 1]))
        if np.all(center_low < window_low):
            low_pivots.append(i)
    return high_pivots, low_pivots


def _fit_line(xs: np.ndarray, ys: np.ndarray) -> tuple[float, float]:
    if len(xs) < 2:
        return 0.0, 0.0
    slope, intercept = np.polyfit(xs, ys, 1)
    return float(slope), float(intercept)


def detect_triangle_consolidation(df: pd.DataFrame, **params) -> dict:
    """Detect triangle consolidation patterns using local pivot lines.

    Args:
        df: OHLC DataFrame with DatetimeIndex and 'High', 'Low' columns.
        **params: Optional parameters:
            - window: number of bars to analyze (default: 30)
            - pivot: lookback bars on each side when finding local pivots (default: 3)
            - epsilon: slope tolerance for flat trendline classification (default: 0.01)

    Returns:
        dict with 'triggered', 'timestamp', 'signal_name', 'details'
    """
    timestamp = df.index[-1].isoformat() if len(df) > 0 else None

    window = int(params.get("window", 30))
    pivot = int(params.get("pivot", 3))
    epsilon = float(params.get("epsilon", 0.01))

    if len(df) < window or window < pivot * 2 + 1:
        return _result(
            timestamp,
            False,
            {
                "type": None,
                "slope_high": None,
                "slope_low": None,
                "contraction_ratio": None,
                "num_high_pivots": None,
                "num_low_pivots": None,
                "window": window,
                "pivot": pivot,
                "epsilon": epsilon,
                "reason": "insufficient_history",
            },
        )

    missing = [c for c in ["High", "Low"] if c not in df.columns]
    if missing:
        return _result(timestamp, False, {"reason": f"missing_columns: {', '.join(missing)}"})

    segment = df.tail(window)
    highs = segment["High"].to_numpy(dtype=float)
    lows = segment["Low"].to_numpy(dtype=float)
    high_pivots, low_pivots = _find_local_pivots(highs, lows, pivot)

    num_high_pivots = len(high_pivots)
    num_low_pivots = len(low_pivots)
    if num_high_pivots < 2 or num_low_pivots < 2:
        return _result(
            timestamp,
            False,
            {
                "type": None,
                "slope_high": None,
                "slope_low": None,
                "contraction_ratio": None,
                "num_high_pivots": num_high_pivots,
                "num_low_pivots": num_low_pivots,
                "window": window,
                "pivot": pivot,
                "epsilon": epsilon,
                "reason": "not_enough_pivots",
            },
        )

    xs_high = np.asarray(high_pivots, dtype=float)
    xs_low = np.asarray(low_pivots, dtype=float)
    ys_high = highs[high_pivots]
    ys_low = lows[low_pivots]

    slope_high, intercept_high = _fit_line(xs_high, ys_high)
    slope_low, intercept_low = _fit_line(xs_low, ys_low)

    x_start = float(min(xs_high[0], xs_low[0]))
    x_end = float(max(xs_high[-1], xs_low[-1]))
    top_start = slope_high * x_start + intercept_high
    bottom_start = slope_low * x_start + intercept_low
    top_end = slope_high * x_end + intercept_high
    bottom_end = slope_low * x_end + intercept_low

    start_range = max(top_start - bottom_start, 0.0)
    end_range = max(top_end - bottom_end, 0.0)
    contraction_ratio = float(end_range / start_range) if start_range > 0 else 1.0

    triangle_type: str | None = None
    if slope_high < -epsilon and slope_low > epsilon:
        triangle_type = "Symmetrical"
    elif abs(slope_high) < epsilon and slope_low > epsilon:
        triangle_type = "Ascending"
    elif slope_high < -epsilon and abs(slope_low) < epsilon:
        triangle_type = "Descending"

    triggered = triangle_type is not None and contraction_ratio < 0.6
    details = {
        "type": triangle_type,
        "slope_high": float(slope_high),
        "slope_low": float(slope_low),
        "contraction_ratio": float(contraction_ratio),
        "num_high_pivots": num_high_pivots,
        "num_low_pivots": num_low_pivots,
        "window": window,
        "pivot": pivot,
        "epsilon": epsilon,
    }

    if not triggered:
        if triangle_type is None:
            reason = "invalid_triangle_type"
        elif contraction_ratio >= 0.6:
            reason = "contraction_ratio_too_large"
        else:
            reason = "unknown"
        details["reason"] = reason

    return _result(timestamp, triggered, details)
