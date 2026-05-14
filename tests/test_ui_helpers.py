"""Lightweight tests for Streamlit UI helper functions."""

from __future__ import annotations

import pandas as pd

from technical_state_scanner.core.scanner import LightweightUniverseResult, ScanResult
from technical_state_scanner.ui.app import (
    build_candlestick_vega_spec,
    format_signal_list,
    get_timeframe_key,
    make_score_summary,
    make_universe_table,
    prepare_chart_data,
)


def _scan_result() -> ScanResult:
    return ScanResult(
        ticker="AAPL.US",
        total_score=20.0,
        pre_multiplier_score=20.0,
        cross_timeframe_all_factor_coverage_multiplier=1.0,
        all_triggered_signals=["Vegas Alignment"],
        base_timeframe_scores={"F1": {"score": 20.0}},
        factor_confluence_scores={"daily": {"tier": "Early", "score": 3, "matched_rule": "F1 + F2"}},
        timeframe_results={
            "weekly": {"triggered_signals": [], "triggered_factors": [], "details": {}},
            "daily": {"triggered_signals": ["Vegas Alignment"], "triggered_factors": ["F1"], "details": {}},
            "4hour": {"triggered_signals": [], "triggered_factors": [], "details": {}},
        },
        notes=[],
    )


def _universe_result() -> LightweightUniverseResult:
    return LightweightUniverseResult(
        ticker="AAPL.US",
        scores={
            "total_score": 20.0,
            "pre_multiplier_score": 20.0,
            "cross_timeframe_all_factor_coverage_multiplier": 1.0,
            "base_timeframe_scores": {"F1": {"score": 20.0}},
        },
        triggered_signals=["Vegas Alignment"],
        triggered_factors=["F1"],
        timeframe_triggered_signals={"weekly": [], "daily": ["Vegas Alignment"], "4hour": []},
        timeframe_triggered_factors={"weekly": [], "daily": ["F1"], "4hour": []},
        factor_confluence={"weekly": {}, "daily": {"score": 3}, "4hour": {}},
        timestamps={"weekly": {}, "daily": {"F1": "2026-01-01T00:00:00+00:00"}, "4hour": {}},
    )


def test_timeframe_labels_map_to_scanner_keys():
    assert get_timeframe_key("4H") == "4hour"
    assert get_timeframe_key("Daily") == "daily"
    assert get_timeframe_key("Weekly") == "weekly"


def test_score_summary_is_persistent_shape_without_display_state():
    summary = make_score_summary(_scan_result())

    assert summary["ticker"] == "AAPL.US"
    assert summary["total_score"] == 20.0
    assert summary["data_source"] == "LongPort OpenAPI"
    assert "primary_state" not in summary
    assert "display_state" not in summary


def test_prepare_chart_data_keeps_ohlc_and_available_indicator_columns():
    frame = pd.DataFrame(
        {
            "Open": [10, 11],
            "High": [12, 13],
            "Low": [9, 10],
            "Close": [11, 12],
            "Volume": [100, 110],
            "EMA12": [10.5, 11.5],
            "EMA144": [10.1, 10.2],
            "EMA169": [10.0, 10.1],
            "EMA576": [9.8, 9.9],
            "EMA676": [9.7, 9.8],
            "VegasLower": [10.0, 10.1],
            "VegasUpper": [10.1, 10.2],
        },
        index=pd.date_range("2026-01-01", periods=2, freq="D", tz="UTC"),
    )

    chart_data = prepare_chart_data(frame)

    assert {"Datetime", "Open", "High", "Low", "Close", "EMA12", "VegasLower", "VegasUpper"}.issubset(
        set(chart_data.columns)
    )
    assert chart_data["is_up"].tolist() == [True, True]


def test_candlestick_spec_is_plain_data_and_includes_indicator_layers():
    chart_data = pd.DataFrame(
        {
            "Datetime": ["2026-01-01", "2026-01-02"],
            "Open": [10, 11],
            "High": [12, 13],
            "Low": [9, 10],
            "Close": [11, 12],
            "EMA12": [10.5, 11.5],
            "VegasLower": [10.0, 10.1],
            "VegasUpper": [10.1, 10.2],
            "is_up": [True, True],
        }
    )

    spec = build_candlestick_vega_spec(chart_data)

    assert isinstance(spec, dict)
    assert len(spec["layer"]) >= 5
    assert "chart_data" not in spec
    assert "figure" not in spec


def test_universe_table_is_lightweight_and_ranked():
    high = _universe_result()
    low = _universe_result()
    low.ticker = "LOW.US"
    low.scores["total_score"] = 1.0

    table = make_universe_table([low, high])

    assert table.iloc[0]["Ticker"] == "AAPL.US"
    assert "Factor Combination" in table.columns
    assert "Latest Signal Time" in table.columns
    assert "chart_data" not in table.columns
    assert "details" not in table.columns
    assert "factor_confluence_summary" not in table.columns
    assert "timestamps" not in table.columns


def test_format_signal_list():
    assert format_signal_list(["F1", "F2"]) == "F1, F2"
    assert format_signal_list([]) == "None"
