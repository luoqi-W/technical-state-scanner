"""F5 - Big Bullish Candle detection."""

from __future__ import annotations

import pandas as pd


def _result(ts: str | None, triggered: bool, details: dict) -> dict:
    return {
        "triggered": triggered,
        "timestamp": ts,
        "signal_name": "Big Bullish Candle",
        "details": details,
    }


def detect_big_bullish_candle(df: pd.DataFrame, **params) -> dict:
    """
    Detect a decisive bullish candle that clearly breaks above the moving-average structure.
    
    Args:
        df: OHLCV DataFrame with DatetimeIndex and columns:
            ['Open', 'High', 'Low', 'Close', 'Volume', 'EMA12', 'EMA144', 'EMA169']
        **params: Optional parameters:
            - min_body_pct: minimum body size as % of open (default: 0.025 = 2.5%)
            - body_ratio_threshold: minimum body ratio vs 20-bar average (default: 1.5)
            - ema_clearance_pct: how much above EMAs (default: 0.015 = 1.5%)
    
    Returns:
        dict with 'triggered', 'timestamp', 'signal_name', 'details'
    """
    ts = df.index[-1].isoformat() if len(df) > 0 else None
    
    min_body_pct = float(params.get("min_body_pct", 0.025))
    body_ratio_threshold = float(params.get("body_ratio_threshold", 1.5))
    ema_clearance_pct = float(params.get("ema_clearance_pct", 0.015))
    
    required_cols = ["Open", "Close", "EMA12", "EMA144", "EMA169"]
    missing = [c for c in required_cols if c not in df.columns]
    if missing:
        return _result(ts, False, {"reason": f"missing_columns: {', '.join(missing)}"})
    
    if len(df) < 20:
        return _result(
            ts,
            False,
            {
                "gain_pct": None,
                "body_size": None,
                "avg_body_size_20": None,
                "body_ratio": None,
                "distance_above_emas_pct": None,
                "reason": "insufficient_history",
            },
        )
    
    row = df.iloc[-1]
    open_price = float(row["Open"])
    close_price = float(row["Close"])
    ema12 = float(row["EMA12"])
    ema144 = float(row["EMA144"])
    ema169 = float(row["EMA169"])
    
    # Condition 1: Close > Open (bullish)
    is_bullish = close_price > open_price
    
    # Condition 2: Body size > min_body_pct
    body_size = close_price - open_price
    gain_pct = (body_size / open_price) if open_price > 0 else 0.0
    has_sufficient_size = gain_pct > min_body_pct
    
    # Condition 3: Body ratio > threshold
    # Calculate average body size of previous 20 bars
    prev_20 = df.iloc[-21:-1]  # Previous 20 bars (excluding current)
    prev_opens = prev_20["Open"].to_numpy(dtype=float)
    prev_closes = prev_20["Close"].to_numpy(dtype=float)
    prev_bodies = abs(prev_closes - prev_opens)
    avg_body_size_20 = float(prev_bodies.mean()) if len(prev_bodies) > 0 else 0.0
    
    body_ratio = (body_size / avg_body_size_20) if avg_body_size_20 > 0 else 0.0
    has_outsized_body = body_ratio > body_ratio_threshold
    
    # Condition 4: Clear escape above all EMAs
    # Close must be > max(EMA12, EMA144, EMA169) * (1 + ema_clearance_pct)
    ema_max = max(ema12, ema144, ema169)
    clearance_threshold = ema_max * (1.0 + ema_clearance_pct)
    is_above_emas = close_price > clearance_threshold
    distance_above_emas = close_price - ema_max
    distance_above_emas_pct = (distance_above_emas / close_price) if close_price > 0 else 0.0
    
    # All conditions must be true
    triggered = is_bullish and has_sufficient_size and has_outsized_body and is_above_emas
    
    details = {
        "gain_pct": float(gain_pct),
        "body_size": float(body_size),
        "avg_body_size_20": float(avg_body_size_20),
        "body_ratio": float(body_ratio),
        "distance_above_emas_pct": float(distance_above_emas_pct),
    }
    
    if not triggered:
        reasons = []
        if not is_bullish:
            reasons.append("not_bullish")
        if not has_sufficient_size:
            reasons.append("insufficient_body_size")
        if not has_outsized_body:
            reasons.append("body_not_outsized")
        if not is_above_emas:
            reasons.append("not_above_emas")
        details["reason"] = ",".join(reasons) if reasons else "unknown"
    
    return _result(ts, triggered, details)
