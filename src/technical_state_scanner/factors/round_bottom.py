"""F3 - Round Bottom detection."""

from __future__ import annotations

import numpy as np
import pandas as pd


def _result(ts: str | None, triggered: bool, details: dict) -> dict:
    return {
        "triggered": triggered,
        "timestamp": ts,
        "signal_name": "Round Bottom",
        "details": details,
    }


def detect_round_bottom(df: pd.DataFrame, **params) -> dict:
    """
    Detect a U-shaped price structure indicating momentum shift from negative to positive.
    
    Args:
        df: OHLCV DataFrame with DatetimeIndex and 'Close' column.
        **params: Optional parameters:
            - window: quadratic fitting window (default: 60)
            - min_r_squared: minimum R² for curve quality (default: 0.7)
    
    Returns:
        dict with 'triggered', 'timestamp', 'signal_name', 'details'
    """
    ts = df.index[-1].isoformat() if len(df) > 0 else None
    
    window = int(params.get("window", 60))
    min_r_squared = float(params.get("min_r_squared", 0.7))
    
    if len(df) < window:
        return _result(
            ts,
            False,
            {
                "a": None,
                "b": None,
                "c": None,
                "r_squared": None,
                "vertex_position": None,
                "window": window,
                "reason": "insufficient_history",
            },
        )
    
    if "Close" not in df.columns:
        return _result(ts, False, {"reason": "missing_Close_column", "window": window})
    
    # Use the last `window` bars
    prices = df["Close"].tail(window).to_numpy(dtype=float)
    x = np.arange(len(prices), dtype=float)
    
    # Fit quadratic polynomial: price ≈ a*x² + b*x + c
    a, b, c = np.polyfit(x, prices, 2)
    y_hat = a * (x**2) + b * x + c
    
    # Calculate R²
    ss_res = float(np.sum((prices - y_hat) ** 2))
    ss_tot = float(np.sum((prices - np.mean(prices)) ** 2))
    r_squared = 1.0 - (ss_res / ss_tot) if ss_tot != 0 else 1.0
    
    # Find vertex position (x-coordinate of minimum for parabola)
    # For f(x) = ax² + bx + c, vertex is at x = -b/(2a)
    vertex_x = -b / (2 * a) if a != 0 else 0.0
    
    # Check if vertex is in the middle 60% of the window [0.2*N, 0.8*N]
    min_x = 0.2 * window
    max_x = 0.8 * window
    vertex_in_range = min_x <= vertex_x <= max_x
    
    # Trigger conditions:
    # 1. a > 0 (concave up, U-shaped)
    # 2. R² > threshold
    # 3. Vertex is in middle 60% of window
    triggered = (a > 0) and (r_squared > min_r_squared) and vertex_in_range
    
    details = {
        "a": float(a),
        "b": float(b),
        "c": float(c),
        "r_squared": float(r_squared),
        "vertex_position": float(vertex_x),
        "window": window,
    }
    
    if not triggered:
        reasons = []
        if a <= 0:
            reasons.append("a_not_positive")
        if r_squared <= min_r_squared:
            reasons.append("r_squared_too_low")
        if not vertex_in_range:
            reasons.append("vertex_outside_range")
        details["reason"] = ",".join(reasons) if reasons else "unknown"
    
    return _result(ts, triggered, details)
