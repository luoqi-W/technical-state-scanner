from __future__ import annotations

import pandas as pd

REQUIRED_COLUMNS = ["EMA12", "EMA144", "EMA169", "EMA576", "EMA676", "Close"]


def _slope(series: pd.Series, lookback: int = 5) -> float:
    if len(series) < lookback + 1:
        return 0.0
    return float((series.iloc[-1] - series.iloc[-1 - lookback]) / lookback)


def _result(ts: str | None, triggered: bool, details: dict) -> dict:
    return {
        "triggered": triggered,
        "timestamp": ts,
        "signal_name": "Vegas Alignment",
        "details": details,
    }


def detect_vegas_alignment(df: pd.DataFrame, **params) -> dict:
    timestamp = df.index[-1].isoformat() if len(df) > 0 else None
    if len(df) < 676:
        return _result(
            timestamp,
            False,
            {
                "mode": None,
                "mode_quality_tier": None,
                "ema12_position": None,
                "overall_spread_pct": None,
                "slope_yellow": None,
                "slope_green": None,
                "distance_between_tunnels": None,
                "reason": "insufficient_history",
            },
        )

    missing = [c for c in REQUIRED_COLUMNS if c not in df.columns]
    if missing:
        return _result(timestamp, False, {"reason": f"missing_columns: {', '.join(missing)}"})

    row = df.iloc[-1]
    yellow_low = min(row["EMA144"], row["EMA169"])
    yellow_high = max(row["EMA144"], row["EMA169"])
    green_low = min(row["EMA576"], row["EMA676"])
    green_high = max(row["EMA576"], row["EMA676"])

    close_price = float(row["Close"])
    overall_max = max(yellow_high, green_high)
    overall_min = min(yellow_low, green_low)
    overall_spread_pct = ((overall_max - overall_min) / close_price) * 100 if close_price else 0.0

    overlap = not (yellow_high < green_low or green_high < yellow_low)
    distance_between_tunnels = max(green_low - yellow_high, yellow_low - green_high, 0.0)
    distance_pct = (distance_between_tunnels / close_price) * 100 if close_price else 0.0

    compression_threshold = float(params.get("compression_threshold_pct", 1.5))
    close_parallel_threshold = float(params.get("close_parallel_threshold_pct", 0.8))

    mode = None
    mode_quality_tier = None
    if overlap and overall_spread_pct < 0.6:
        mode = "full_overlap"
        mode_quality_tier = "A"
    elif overall_spread_pct < compression_threshold:
        mode = "tight_compression"
        mode_quality_tier = "B"
    elif distance_pct <= close_parallel_threshold:
        mode = "parallel_close"
        mode_quality_tier = "C"
    elif overlap:
        mode = "nested_interlaced"
        mode_quality_tier = "A"

    ema12 = float(row["EMA12"])
    tunnel_low = min(yellow_low, green_low)
    tunnel_high = max(yellow_high, green_high)
    if tunnel_low <= ema12 <= tunnel_high:
        ema12_position = "INSIDE_TUNNEL"
    elif ema12 > tunnel_high:
        ema12_position = "ABOVE_TUNNEL"
    else:
        ema12_position = "BELOW_TUNNEL"

    details = {
        "mode": mode,
        "mode_quality_tier": mode_quality_tier,
        "ema12_position": ema12_position,
        "overall_spread_pct": float(overall_spread_pct),
        "slope_yellow": _slope((df["EMA144"] + df["EMA169"]) / 2.0),
        "slope_green": _slope((df["EMA576"] + df["EMA676"]) / 2.0),
        "distance_between_tunnels": float(distance_between_tunnels),
    }

    triggered = mode is not None
    if not triggered:
        details["reason"] = "no_vegas_alignment"

    return _result(timestamp, triggered, details)
