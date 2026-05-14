"""Aggregate independent factor signals without ranking or stage logic."""

from __future__ import annotations

import pandas as pd

from technical_state_scanner.factors.big_candle import detect_big_bullish_candle
from technical_state_scanner.factors.ema12_liftoff import detect_ema12_liftoff
from technical_state_scanner.factors.round_bottom import detect_round_bottom
from technical_state_scanner.factors.triangle import detect_triangle_consolidation
from technical_state_scanner.factors.vegas_alignment import detect_vegas_alignment
from technical_state_scanner.factors.volume_surge import detect_volume_surge
from technical_state_scanner.core.scoring import calculate_score


FACTOR_FUNCTIONS: dict[str, callable] = {
    "F1": detect_vegas_alignment,
    "F2": detect_ema12_liftoff,
    "F3": detect_round_bottom,
    "F4": detect_triangle_consolidation,
    "F5": detect_big_bullish_candle,
    "F6": detect_volume_surge,
}


def aggregate_signals(df: pd.DataFrame, **params) -> dict:
    """Run all factor detectors and collect triggered signals.

    Args:
        df: OHLCV DataFrame to evaluate.
        **params: Optional parameters forwarded to each factor detector.

    Returns:
        dict containing triggered_signals, triggered_factors, and details for all factors.
    """
    details: dict[str, dict] = {}
    triggered_signals: list[str] = []
    triggered_factors: list[str] = []

    for factor_id, func in FACTOR_FUNCTIONS.items():
        result = func(df, **params)
        details[factor_id] = result
        if result.get("triggered"):
            triggered_signals.append(result.get("signal_name"))
            triggered_factors.append(factor_id)

    return {
        "triggered_signals": triggered_signals,
        "triggered_factors": triggered_factors,
        "details": details,
    }


def aggregate_signals_with_scoring(
    timeframe_data: dict[str, pd.DataFrame],
    **params,
) -> dict:
    """Run all factor detectors across multiple timeframes and calculate multi-layer score.

    Args:
        timeframe_data: Dict mapping timeframe name to OHLCV DataFrame
                       (e.g., {"daily": df_daily, "weekly": df_weekly, "4hour": df_4h})
        **params: Optional parameters forwarded to each factor detector.

    Returns:
        dict containing:
        - triggered_signals: all signals triggered across all timeframes
        - timeframes: dict mapping timeframe to aggregated signals and score
        - scoring: multi-layer scoring results
        - total_score: final calculated score
    """
    timeframe_results = {}
    all_signals_list = []

    # Run aggregation on each timeframe
    for timeframe, df in timeframe_data.items():
        result = aggregate_signals(df, **params)
        timeframe_results[timeframe] = result
        all_signals_list.extend(result.get("triggered_signals", []))

    # Calculate multi-layer score
    score_result = calculate_score(
        all_triggered_signals={
            tf: result.get("triggered_signals", [])
            for tf, result in timeframe_results.items()
        },
        timeframe_signals_map=timeframe_results,
    )

    # Compile comprehensive output
    return {
        "triggered_signals": list(set(all_signals_list)),  # Deduplicate signals
        "timeframes": {
            tf: {
                "triggered_signals": result.get("triggered_signals", []),
                "triggered_factors": result.get("triggered_factors", []),
                "details": result.get("details", {}),
            }
            for tf, result in timeframe_results.items()
        },
        "scoring": {
            "base_timeframe_scores": score_result.base_timeframe_scores,
            "factor_confluence_scores": score_result.factor_confluence_scores,
            "cross_timeframe_all_factor_coverage_multiplier": score_result.cross_timeframe_all_factor_coverage_multiplier,
            "pre_multiplier_score": score_result.pre_multiplier_score,
            "total_score": score_result.total_score,
        },
        "total_score": score_result.total_score,
    }
