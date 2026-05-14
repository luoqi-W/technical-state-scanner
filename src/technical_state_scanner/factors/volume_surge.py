"""F6 - Volume Surge detection."""

from __future__ import annotations

import pandas as pd


def _result(ts: str | None, triggered: bool, details: dict) -> dict:
    return {
        "triggered": triggered,
        "timestamp": ts,
        "signal_name": "Volume Surge",
        "details": details,
    }


def detect_volume_surge(df: pd.DataFrame, **params) -> dict:
    """
    Detect volume surge indicating strong participation in price movement.
    
    Args:
        df: OHLCV DataFrame with DatetimeIndex and 'Volume' column.
        **params: Optional parameters:
            - surge_ratio: minimum volume ratio vs 20-bar average (default: 1.5)
    
    Returns:
        dict with 'triggered', 'timestamp', 'signal_name', 'details'
    """
    ts = df.index[-1].isoformat() if len(df) > 0 else None
    
    surge_ratio = float(params.get("surge_ratio", 1.5))
    
    if "Volume" not in df.columns:
        return _result(ts, False, {"reason": "missing_Volume_column"})
    
    if len(df) < 20:
        return _result(
            ts,
            False,
            {
                "current_volume": None,
                "avg_volume_20": None,
                "surge_ratio": None,
                "reason": "insufficient_history",
            },
        )
    
    # Current volume (the last bar)
    current_volume = float(df["Volume"].iloc[-1])
    
    # Average volume of previous 20 bars (not including current)
    prev_20 = df["Volume"].iloc[-21:-1]
    avg_volume_20 = float(prev_20.mean())
    
    # Calculate actual surge ratio
    actual_ratio = (current_volume / avg_volume_20) if avg_volume_20 > 0 else 0.0
    
    # Trigger if current volume exceeds threshold
    triggered = actual_ratio > surge_ratio
    
    details = {
        "current_volume": current_volume,
        "avg_volume_20": avg_volume_20,
        "surge_ratio": float(actual_ratio),
    }
    
    if not triggered:
        details["reason"] = f"volume_ratio_below_threshold ({actual_ratio:.2f} <= {surge_ratio})"
    
    return _result(ts, triggered, details)
