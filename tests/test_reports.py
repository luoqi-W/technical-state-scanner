"""Tests for scanner report output helpers."""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from technical_state_scanner.core.csv_output import (
    lightweight_universe_results_to_dataframe,
    scan_result_to_structured_output,
    write_single_scan_result_to_json,
    write_universe_results_to_csv,
)
from technical_state_scanner.core.scanner import LightweightUniverseResult, ScanResult


def _sample_lightweight_result(error: str | None = None) -> LightweightUniverseResult:
    return LightweightUniverseResult(
        ticker="AAPL.US",
        scores={
            "total_score": 48.5,
            "pre_multiplier_score": 48.5,
            "cross_timeframe_all_factor_coverage_multiplier": 1.0,
            "base_timeframe_scores": {"F1": {"score": 10.0}},
        },
        triggered_signals=["Vegas Alignment", "Round Bottom"],
        triggered_factors=["F1", "F3"],
        timeframe_triggered_signals={
            "weekly": ["Round Bottom"],
            "daily": ["Vegas Alignment"],
            "4hour": [],
        },
        timeframe_triggered_factors={
            "weekly": ["F3"],
            "daily": ["F1"],
            "4hour": [],
        },
        factor_confluence={
            "weekly": {"tier": None, "score": 0, "matched_rule": None},
            "daily": {"tier": "Early", "score": 3, "matched_rule": "F1 + F2"},
            "4hour": {"tier": None, "score": 0, "matched_rule": None},
        },
        timestamps={
            "weekly": {"F3": "2026-01-03T00:00:00+00:00"},
            "daily": {"F1": "2026-01-04T00:00:00+00:00"},
            "4hour": {},
        },
        error=error,
    )


def _sample_scan_result() -> ScanResult:
    return ScanResult(
        ticker="AAPL.US",
        total_score=48.5,
        pre_multiplier_score=48.5,
        cross_timeframe_all_factor_coverage_multiplier=1.0,
        all_triggered_signals=["Vegas Alignment", "Round Bottom"],
        base_timeframe_scores={"F1": {"score": 10.0}},
        factor_confluence_scores={
            "weekly": {"tier": None, "score": 0, "matched_rule": None},
            "daily": {"tier": "Early", "score": 3, "matched_rule": "F1 + F2"},
            "4hour": {"tier": None, "score": 0, "matched_rule": None},
        },
        timeframe_results={
            "weekly": {
                "triggered_signals": ["Round Bottom"],
                "triggered_factors": ["F3"],
                "factor_confluence_tier": None,
                "factor_confluence_score": 0,
                "details": {
                    "F3": {
                        "triggered": True,
                        "timestamp": "2026-01-03T00:00:00+00:00",
                        "signal_name": "Round Bottom",
                        "details": {"a": 0.01, "r_squared": 0.8},
                    }
                },
            },
            "daily": {
                "triggered_signals": ["Vegas Alignment"],
                "triggered_factors": ["F1"],
                "factor_confluence_tier": "Early",
                "factor_confluence_score": 3,
                "details": {
                    "F1": {
                        "triggered": True,
                        "timestamp": "2026-01-04T00:00:00+00:00",
                        "signal_name": "Vegas Alignment",
                        "details": {
                            "mode": "nested_interlaced",
                            "overall_spread_pct": 0.4,
                        },
                    }
                },
            },
            "4hour": {
                "triggered_signals": [],
                "triggered_factors": [],
                "factor_confluence_tier": None,
                "factor_confluence_score": 0,
                "details": {
                    "F1": {
                        "triggered": False,
                        "timestamp": "2026-01-04T16:00:00+00:00",
                        "signal_name": "Vegas Alignment",
                        "details": {"reason": "no_vegas_alignment"},
                    }
                },
            },
        },
        notes=["Signals are independent; this output does not imply sequential stage progression."],
    )


def test_universe_csv_file_is_created_under_reports(tmp_path):
    csv_path = write_universe_results_to_csv([_sample_lightweight_result()], base_path=tmp_path)

    path = Path(csv_path)
    assert path.exists()
    assert path.parent == tmp_path / "reports"
    assert path.name.startswith("universe_scan_")


def test_universe_csv_has_required_columns(tmp_path):
    csv_path = write_universe_results_to_csv([_sample_lightweight_result()], base_path=tmp_path)
    df = pd.read_csv(csv_path)

    required_columns = [
        "ticker",
        "total_score",
        "pre_multiplier_score",
        "cross_timeframe_all_factor_coverage_multiplier",
        "all_triggered_signals",
        "weekly_triggered_signals",
        "weekly_triggered_factors",
        "weekly_score",
        "daily_triggered_signals",
        "daily_triggered_factors",
        "daily_score",
        "four_hour_triggered_signals",
        "four_hour_triggered_factors",
        "four_hour_score",
        "factor_confluence_summary",
        "data_source",
        "timestamps",
        "failed_reason",
    ]
    for column in required_columns:
        assert column in df.columns


def test_universe_lightweight_results_can_be_exported():
    df = lightweight_universe_results_to_dataframe([_sample_lightweight_result()])

    assert len(df) == 1
    assert df.loc[0, "ticker"] == "AAPL.US"
    assert df.loc[0, "total_score"] == 48.5
    assert df.loc[0, "daily_triggered_factors"] == "F1"
    assert df.loc[0, "four_hour_triggered_signals"] == "None"


def test_single_scan_structured_output_preserves_nested_details():
    output = scan_result_to_structured_output(_sample_scan_result())

    assert output["ticker"] == "AAPL.US"
    assert output["total_score"] == 48.5
    assert output["scoring_breakdown"]["base_timeframe_scores"]["F1"]["score"] == 10.0
    assert output["timeframes"]["daily"]["details"]["F1"]["details"]["mode"] == "nested_interlaced"
    assert output["factor_confluence"]["daily"]["tier"] == "Early"
    assert output["timestamps"]["weekly"]["F3"] == "2026-01-03T00:00:00+00:00"
    assert "primary_state" not in output
    assert "display_state" not in output


def test_single_scan_json_file_is_written(tmp_path):
    json_path = write_single_scan_result_to_json(_sample_scan_result(), base_path=tmp_path)

    payload = json.loads(Path(json_path).read_text(encoding="utf-8"))
    assert payload["ticker"] == "AAPL.US"
    assert payload["timeframes"]["daily"]["triggered_factors"] == ["F1"]


def test_universe_csv_excludes_chart_data_and_figure_objects():
    df = lightweight_universe_results_to_dataframe([_sample_lightweight_result()])
    serialized = df.to_csv(index=False)

    forbidden_tokens = ["chart_data", "chart_image", "figure", "fig", "plotly", "matplotlib"]
    for token in forbidden_tokens:
        assert token not in df.columns
        assert token not in serialized


def test_failed_symbol_is_represented_clearly():
    df = lightweight_universe_results_to_dataframe([
        _sample_lightweight_result(error="LongPort returned empty candlestick data.")
    ])

    assert df.loc[0, "failed_reason"] == "LongPort returned empty candlestick data."

