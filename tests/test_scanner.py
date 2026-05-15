"""Tests for scanner module."""

from __future__ import annotations

import pytest
import pandas as pd

from technical_state_scanner.core.scanner import (
    LightweightUniverseResult,
    ScanResult,
    _to_lightweight_universe_result,
    load_named_universe,
    load_symbols_from_file,
    scan_universe_lightweight,
    scan_results_to_dataframe,
)


class TestScanResult:
    """Test ScanResult dataclass."""

    def test_scan_result_creation(self):
        """Test creating a ScanResult."""
        result = ScanResult(
            ticker="AAPL.US",
            total_score=50.5,
            pre_multiplier_score=40.0,
            cross_timeframe_all_factor_coverage_multiplier=1.0,
            all_triggered_signals=["Vegas Alignment", "Round Bottom"],
            base_timeframe_scores={"F1": {"score": 10}},
            factor_confluence_scores={"daily": {"tier": "A", "score": 22}},
            timeframe_results={
                "weekly": {"triggered_signals": ["Vegas Alignment"]},
                "daily": {"triggered_signals": ["Round Bottom"]},
                "4hour": {"triggered_signals": []},
            },
            notes=["Test note"],
        )

        assert result.ticker == "AAPL.US"
        assert result.total_score == 50.5
        assert len(result.all_triggered_signals) == 2

    def test_scan_result_with_error(self):
        """Test creating a ScanResult with error."""
        result = ScanResult(
            ticker="INVALID",
            total_score=0.0,
            pre_multiplier_score=0.0,
            cross_timeframe_all_factor_coverage_multiplier=1.0,
            all_triggered_signals=[],
            base_timeframe_scores={},
            factor_confluence_scores={},
            timeframe_results={},
            notes=["Error loading data"],
            error="LongPort API error",
        )

        assert result.error is not None
        assert result.total_score == 0.0


class TestLightweightUniverseResult:
    """Test lightweight universe scan output."""

    def test_lightweight_result_contains_only_universe_summary_fields(self):
        detailed = ScanResult(
            ticker="AAPL.US",
            total_score=42.0,
            pre_multiplier_score=42.0,
            cross_timeframe_all_factor_coverage_multiplier=1.0,
            all_triggered_signals=["Vegas Alignment"],
            base_timeframe_scores={"F1": {"score": 10}},
            factor_confluence_scores={"daily": {"tier": None, "score": 0, "matched_rule": None}},
            timeframe_results={
                "weekly": {
                    "triggered_signals": [],
                    "triggered_factors": [],
                    "factor_confluence_tier": None,
                    "factor_confluence_score": 0,
                    "details": {},
                },
                "daily": {
                    "triggered_signals": ["Vegas Alignment"],
                    "triggered_factors": ["F1"],
                    "factor_confluence_tier": None,
                    "factor_confluence_score": 0,
                    "details": {
                        "F1": {
                            "timestamp": "2026-01-01T00:00:00+00:00",
                            "details": {"overall_spread_pct": 0.4},
                        }
                    },
                },
                "4hour": {
                    "triggered_signals": [],
                    "triggered_factors": [],
                    "factor_confluence_tier": None,
                    "factor_confluence_score": 0,
                    "details": {},
                },
            },
            notes=[],
        )

        result = _to_lightweight_universe_result(detailed)
        result_dict = result.to_dict()

        assert isinstance(result, LightweightUniverseResult)
        assert result_dict["ticker"] == "AAPL.US"
        assert result_dict["scores"]["total_score"] == 42.0
        assert result_dict["triggered_signals"] == ["Vegas Alignment"]
        assert result_dict["triggered_factors"] == ["F1"]
        assert result_dict["timestamps"]["daily"]["F1"] == "2026-01-01T00:00:00+00:00"
        assert "timeframe_results" not in result_dict
        assert "details" not in result_dict

    def test_scan_universe_lightweight_sorts_by_total_score(self, monkeypatch):
        def fake_scan_universe(symbols, count=300):
            return [
                ScanResult(
                    ticker="LOW.US",
                    total_score=1.0,
                    pre_multiplier_score=1.0,
                    cross_timeframe_all_factor_coverage_multiplier=1.0,
                    all_triggered_signals=[],
                    base_timeframe_scores={},
                    factor_confluence_scores={},
                    timeframe_results={"weekly": {}, "daily": {}, "4hour": {}},
                    notes=[],
                ),
                ScanResult(
                    ticker="HIGH.US",
                    total_score=9.0,
                    pre_multiplier_score=9.0,
                    cross_timeframe_all_factor_coverage_multiplier=1.0,
                    all_triggered_signals=[],
                    base_timeframe_scores={},
                    factor_confluence_scores={},
                    timeframe_results={"weekly": {}, "daily": {}, "4hour": {}},
                    notes=[],
                ),
            ]

        monkeypatch.setattr("technical_state_scanner.core.scanner.scan_universe", fake_scan_universe)

        results = scan_universe_lightweight(["LOW", "HIGH"])

        assert [result.ticker for result in results] == ["HIGH.US", "LOW.US"]

    def test_load_symbols_from_txt_file(self, tmp_path):
        path = tmp_path / "watchlist.txt"
        path.write_text("AAPL\n# comment\ncrcl.us\nAAPL\n", encoding="utf-8")

        assert load_symbols_from_file(path) == ["AAPL.US", "CRCL.US"]

    def test_load_symbols_from_comma_separated_txt_file(self, tmp_path):
        path = tmp_path / "watchlist.txt"
        path.write_text("AAPL, MSFT,crcl.us\n# comment\nTSLA\n", encoding="utf-8")

        assert load_symbols_from_file(path) == ["AAPL.US", "MSFT.US", "CRCL.US", "TSLA.US"]

    def test_load_symbols_from_csv_file_with_symbol_column(self, tmp_path):
        path = tmp_path / "watchlist.csv"
        path.write_text("ticker,name\nTSLA,Tesla\nMSFT,Microsoft\n", encoding="utf-8")

        assert load_symbols_from_file(path, symbol_column="ticker") == ["TSLA.US", "MSFT.US"]

    def test_load_named_universe_reports_missing_local_file(self, tmp_path):
        with pytest.raises(FileNotFoundError, match="No local sp500 universe list found"):
            load_named_universe("sp500", base_path=tmp_path)


class TestScanResultsToDataFrame:
    """Test conversion of scan results to DataFrame."""

    def test_single_result_to_dataframe(self):
        """Test converting a single ScanResult to DataFrame."""
        result = ScanResult(
            ticker="AAPL.US",
            total_score=50.5,
            pre_multiplier_score=40.0,
            cross_timeframe_all_factor_coverage_multiplier=1.0,
            all_triggered_signals=["Vegas Alignment"],
            base_timeframe_scores={},
            factor_confluence_scores={},
            timeframe_results={
                "weekly": {
                    "triggered_signals": ["Vegas Alignment"],
                    "triggered_factors": ["F1"],
                    "factor_confluence_tier": None,
                    "factor_confluence_score": 0,
                    "details": {},
                },
                "daily": {
                    "triggered_signals": [],
                    "triggered_factors": [],
                    "factor_confluence_tier": None,
                    "factor_confluence_score": 0,
                    "details": {},
                },
                "4hour": {
                    "triggered_signals": [],
                    "triggered_factors": [],
                    "factor_confluence_tier": None,
                    "factor_confluence_score": 0,
                    "details": {},
                },
            },
            notes=["Test"],
        )

        df = scan_results_to_dataframe([result])

        assert isinstance(df, pd.DataFrame)
        assert len(df) == 1
        assert df.loc[0, "ticker"] == "AAPL.US"
        assert df.loc[0, "total_score"] == 50.5
        assert "Vegas Alignment" in df.loc[0, "all_triggered_signals"]

    def test_multiple_results_to_dataframe(self):
        """Test converting multiple ScanResults to DataFrame."""
        results = []
        for i, symbol in enumerate(["AAPL.US", "TSLA.US", "MSFT.US"]):
            result = ScanResult(
                ticker=symbol,
                total_score=50.0 + i * 10,
                pre_multiplier_score=40.0,
                cross_timeframe_all_factor_coverage_multiplier=1.0,
                all_triggered_signals=["Vegas Alignment"],
                base_timeframe_scores={},
                factor_confluence_scores={},
                timeframe_results={
                    "weekly": {
                        "triggered_signals": [],
                        "triggered_factors": [],
                        "factor_confluence_tier": None,
                        "factor_confluence_score": 0,
                        "details": {},
                    },
                    "daily": {
                        "triggered_signals": [],
                        "triggered_factors": [],
                        "factor_confluence_tier": None,
                        "factor_confluence_score": 0,
                        "details": {},
                    },
                    "4hour": {
                        "triggered_signals": [],
                        "triggered_factors": [],
                        "factor_confluence_tier": None,
                        "factor_confluence_score": 0,
                        "details": {},
                    },
                },
                notes=[],
            )
            results.append(result)

        df = scan_results_to_dataframe(results)

        assert len(df) == 3
        assert list(df["ticker"]) == ["AAPL.US", "TSLA.US", "MSFT.US"]
        assert df["total_score"].tolist() == [50.0, 60.0, 70.0]

    def test_dataframe_has_all_required_columns(self):
        """Test that DataFrame has all required columns."""
        result = ScanResult(
            ticker="TEST.US",
            total_score=100.0,
            pre_multiplier_score=50.0,
            cross_timeframe_all_factor_coverage_multiplier=1.0,
            all_triggered_signals=["Vegas Alignment", "Round Bottom"],
            base_timeframe_scores={},
            factor_confluence_scores={},
            timeframe_results={
                "weekly": {
                    "triggered_signals": ["Vegas Alignment"],
                    "triggered_factors": ["F1"],
                    "factor_confluence_tier": "A",
                    "factor_confluence_score": 22,
                    "details": {},
                },
                "daily": {
                    "triggered_signals": ["Round Bottom"],
                    "triggered_factors": ["F3"],
                    "factor_confluence_tier": None,
                    "factor_confluence_score": 0,
                    "details": {},
                },
                "4hour": {
                    "triggered_signals": [],
                    "triggered_factors": [],
                    "factor_confluence_tier": None,
                    "factor_confluence_score": 0,
                    "details": {},
                },
            },
            notes=["Test note"],
        )

        df = scan_results_to_dataframe([result])

        required_cols = [
            "ticker",
            "total_score",
            "pre_multiplier_score",
            "cross_timeframe_all_factor_coverage_multiplier",
            "all_triggered_signals",
            "weekly_triggered_signals",
            "weekly_triggered_factors",
            "weekly_confluence_tier",
            "weekly_confluence_score",
            "daily_triggered_signals",
            "daily_triggered_factors",
            "daily_confluence_tier",
            "daily_confluence_score",
            "4hour_triggered_signals",
            "4hour_triggered_factors",
            "4hour_confluence_tier",
            "4hour_confluence_score",
            "data_source",
            "notes",
        ]

        for col in required_cols:
            assert col in df.columns, f"Missing required column: {col}"

    def test_dataframe_signal_formatting(self):
        """Test that signals are properly formatted in DataFrame."""
        result = ScanResult(
            ticker="TEST.US",
            total_score=50.0,
            pre_multiplier_score=40.0,
            cross_timeframe_all_factor_coverage_multiplier=1.0,
            all_triggered_signals=["Signal1", "Signal2"],
            base_timeframe_scores={},
            factor_confluence_scores={},
            timeframe_results={
                "weekly": {
                    "triggered_signals": ["Signal1"],
                    "triggered_factors": ["F1"],
                    "factor_confluence_tier": None,
                    "factor_confluence_score": 0,
                    "details": {},
                },
                "daily": {
                    "triggered_signals": ["Signal2"],
                    "triggered_factors": ["F3"],
                    "factor_confluence_tier": None,
                    "factor_confluence_score": 0,
                    "details": {},
                },
                "4hour": {
                    "triggered_signals": [],
                    "triggered_factors": [],
                    "factor_confluence_tier": None,
                    "factor_confluence_score": 0,
                    "details": {},
                },
            },
            notes=[],
        )

        df = scan_results_to_dataframe([result])

        # Signals should be joined by semicolon
        assert df.loc[0, "all_triggered_signals"] == "Signal1;Signal2"
        assert df.loc[0, "weekly_triggered_signals"] == "Signal1"
        assert df.loc[0, "daily_triggered_signals"] == "Signal2"
        assert df.loc[0, "4hour_triggered_signals"] == "None"
