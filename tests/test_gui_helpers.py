"""Tests for desktop GUI helper functions without launching Qt."""

from __future__ import annotations

import pandas as pd

from technical_state_scanner.core.scanner import ScanResult
from technical_state_scanner.gui.charts import (
    build_summary_model,
    build_factor_combination_summary,
    build_status_sentence,
    format_list,
    get_latest_snapshot,
    get_timeframe_key,
    get_triggered_factor_labels,
    prepare_price_panel_data,
    prepare_volume_panel_data,
)
from technical_state_scanner.gui.widgets import (
    format_advanced_summary_text,
    format_details_text,
    format_summary_html,
    format_timeframe_summary_text,
)
from technical_state_scanner.gui.app import _set_plot_style


def _scan_result() -> ScanResult:
    return ScanResult(
        ticker="CRCL.US",
        total_score=0.0,
        pre_multiplier_score=0.0,
        cross_timeframe_all_factor_coverage_multiplier=1.0,
        all_triggered_signals=[],
        base_timeframe_scores={},
        factor_confluence_scores={
            "daily": {"tier": None, "score": 0, "matched_rule": None},
        },
        timeframe_results={
            "daily": {
                "triggered_signals": [],
                "triggered_factors": [],
                "factor_confluence_tier": None,
                "factor_confluence_score": 0,
                "details": {"F1": {"triggered": False}},
            }
        },
        notes=["No technical signals detected across all timeframes."],
    )


def _frame() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "Open": [10.0, 11.0],
            "High": [12.0, 13.0],
            "Low": [9.0, 10.0],
            "Close": [11.0, 12.0],
            "Volume": [1000, 1500],
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


def test_desktop_timeframe_mapping():
    assert get_timeframe_key("4H") == "4hour"
    assert get_timeframe_key("Daily") == "daily"
    assert get_timeframe_key("Weekly") == "weekly"


def test_summary_model_preserves_total_score_across_timeframe_context():
    frames = {"daily": _frame()}
    summary = build_summary_model(_scan_result(), frames, "daily")

    assert summary["ticker"] == "CRCL.US"
    assert summary["latest_close"] == 12.0
    assert summary["total_score"] == 0.0
    assert summary["active_timeframe"] == "daily"
    assert summary["data_source"] == "LongPort OpenAPI"
    assert "primary_state" not in summary
    assert "display_state" not in summary


def test_chart_helpers_keep_price_volume_indicator_data():
    price = prepare_price_panel_data(_frame())
    volume = prepare_volume_panel_data(_frame())

    assert {"Close", "EMA12", "EMA144", "EMA169", "EMA576", "EMA676", "VegasLower", "VegasUpper"}.issubset(
        set(price.columns)
    )
    assert volume["Volume"].tolist() == [1000, 1500]


def test_latest_snapshot_and_formatters():
    snapshot = get_latest_snapshot(_frame())

    assert snapshot["latest_close"] == 12.0
    assert snapshot["latest_date"].startswith("2026-01-02")
    assert format_list(["F1", "F6"]) == "F1, F6"
    assert format_list([]) == "None"


def test_factor_label_and_details_formatting():
    timeframe_result = {
        "triggered_factors": ["F1", "F6"],
        "triggered_signals": ["Vegas Alignment", "Volume Surge"],
        "details": {"F1": {"triggered": True}},
    }

    labels = get_triggered_factor_labels(timeframe_result)
    details = format_details_text(timeframe_result)

    assert labels == ["F1: Vegas Alignment", "F6: Volume Surge"]
    assert '"F1"' in details
    assert "primary_state" not in details
    assert "display_state" not in details


def test_friendly_timeframe_summary_hides_raw_dicts_by_default():
    timeframe_result = {
        "triggered_factors": ["F3"],
        "triggered_signals": ["Round Bottom"],
        "factor_confluence_tier": "C+",
        "factor_confluence_score": 12,
        "details": {"F3": {"a": 0.01}},
    }

    text = format_timeframe_summary_text("Daily", timeframe_result)

    assert "Selected Timeframe: Daily" in text
    assert "- F3" in text
    assert "Round Bottom detected on Daily timeframe." in text
    assert "C+ pattern detected on Daily" in text
    assert "{" not in text
    assert "base_signal_score" not in text
    assert "timeframe_multiplier" not in text


def test_status_and_combination_are_plain_language():
    result = _scan_result()
    timeframe_result = {
        "triggered_factors": ["F3"],
        "triggered_signals": ["Round Bottom"],
        "factor_confluence_tier": "C+",
    }

    assert build_status_sentence(result, "Daily", timeframe_result) == "Daily Round Bottom detected."
    assert build_factor_combination_summary("Daily", timeframe_result) == "C+ pattern detected on Daily"


def test_summary_html_contains_error_and_no_forbidden_state():
    result = _scan_result()
    result.error = "LongPort returned empty candles."
    summary = build_summary_model(result, {"daily": _frame()}, "daily")
    html = format_summary_html(summary)

    assert "LongPort returned empty candles." in html
    assert "LongPort OpenAPI" in html
    assert "Pre-multiplier" not in html
    assert "Coverage multiplier" not in html
    assert "matched_rule" not in html
    assert "primary_state" not in html
    assert "display_state" not in html


def test_advanced_summary_contains_backend_fields_only_for_optional_panel():
    summary = build_summary_model(_scan_result(), {"daily": _frame()}, "daily")
    text = format_advanced_summary_text(summary)

    assert "pre_multiplier_score" in text
    assert "cross_timeframe_all_factor_coverage_multiplier" in text


def test_plot_style_supports_pyqtgraph_plot_item_without_set_background():
    class AxisStub:
        def __init__(self):
            self.pen = None

        def setTextPen(self, pen):
            self.pen = pen

    class ViewBoxStub:
        def __init__(self):
            self.background = None

        def setBackgroundColor(self, color):
            self.background = color

    class PlotItemStub:
        def __init__(self):
            self.view_box = ViewBoxStub()
            self.axes = {"left": AxisStub(), "bottom": AxisStub()}
            self.title = None
            self.grid = None

        def getViewBox(self):
            return self.view_box

        def showGrid(self, x, y, alpha):
            self.grid = (x, y, alpha)

        def setTitle(self, title, color, size):
            self.title = (title, color, size)

        def getAxis(self, name):
            return self.axes[name]

    plot = PlotItemStub()
    _set_plot_style(plot, "Price")

    assert plot.view_box.background == "#0d1117"
    assert plot.grid == (True, True, 0.22)
    assert plot.title[0] == "Price"
