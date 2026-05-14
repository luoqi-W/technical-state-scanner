"""Tests for CSV output module."""

from __future__ import annotations

import os
import tempfile
from pathlib import Path

import pytest
import pandas as pd

from technical_state_scanner.core.csv_output import (
    ensure_reports_directory,
    write_scan_results_to_csv,
    write_summary_csv,
    load_scan_results_from_csv,
)
from technical_state_scanner.core.scanner import ScanResult


@pytest.fixture
def temp_dir():
    """Create a temporary directory for test files."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield tmpdir


@pytest.fixture
def sample_results():
    """Create sample ScanResult objects for testing."""
    return [
        ScanResult(
            ticker="AAPL.US",
            total_score=100.5,
            pre_multiplier_score=50.0,
            cross_timeframe_all_factor_coverage_multiplier=2.0,
            all_triggered_signals=["Vegas Alignment", "Round Bottom"],
            base_timeframe_scores={"F1": {"score": 10}},
            factor_confluence_scores={"daily": {"tier": "A", "score": 22}},
            timeframe_results={
                "weekly": {
                    "triggered_signals": ["Vegas Alignment"],
                    "triggered_factors": ["F1"],
                    "factor_confluence_tier": None,
                    "factor_confluence_score": 0,
                    "details": {},
                },
                "daily": {
                    "triggered_signals": ["Round Bottom"],
                    "triggered_factors": ["F3"],
                    "factor_confluence_tier": "A",
                    "factor_confluence_score": 22,
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
        ),
        ScanResult(
            ticker="TSLA.US",
            total_score=75.0,
            pre_multiplier_score=40.0,
            cross_timeframe_all_factor_coverage_multiplier=1.0,
            all_triggered_signals=["EMA12 Lift-Off"],
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
                    "triggered_signals": ["EMA12 Lift-Off"],
                    "triggered_factors": ["F2"],
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
        ),
    ]


class TestEnsureReportsDirectory:
    """Test reports directory creation."""

    def test_create_reports_directory(self, temp_dir):
        """Test creating reports directory."""
        reports_path = ensure_reports_directory(temp_dir)
        assert reports_path.exists()
        assert reports_path.is_dir()
        assert reports_path.name == "reports"

    def test_existing_reports_directory(self, temp_dir):
        """Test that existing reports directory is not recreated."""
        reports_path = ensure_reports_directory(temp_dir)
        reports_path_second = ensure_reports_directory(temp_dir)
        assert reports_path == reports_path_second


class TestWriteScanResultsToCsv:
    """Test CSV writing functionality."""

    def test_write_scan_results(self, temp_dir, sample_results):
        """Test writing scan results to CSV."""
        csv_path = write_scan_results_to_csv(sample_results, base_path=temp_dir)
        
        assert Path(csv_path).exists()
        assert csv_path.endswith(".csv")
        
        # Verify file content
        df = pd.read_csv(csv_path)
        assert len(df) == 2
        assert "ticker" in df.columns
        assert "total_score" in df.columns

    def test_csv_filename_format(self, temp_dir, sample_results):
        """Test that CSV filename follows expected pattern."""
        csv_path = write_scan_results_to_csv(sample_results, base_path=temp_dir)
        filename = Path(csv_path).name
        
        assert filename.startswith("scan_results_")
        assert filename.endswith(".csv")

    def test_custom_output_path(self, temp_dir, sample_results):
        """Test writing to a custom output path."""
        custom_path = Path(temp_dir) / "custom_output.csv"
        csv_path = write_scan_results_to_csv(sample_results, output_path=str(custom_path))
        
        assert Path(csv_path).exists()
        assert Path(csv_path).name == "custom_output.csv"

    def test_csv_contains_all_rows(self, temp_dir, sample_results):
        """Test that all results are written to CSV."""
        csv_path = write_scan_results_to_csv(sample_results, base_path=temp_dir)
        df = pd.read_csv(csv_path)
        
        assert len(df) == len(sample_results)
        assert set(df["ticker"]) == {"AAPL.US", "TSLA.US"}


class TestWriteSummaryCsv:
    """Test summary CSV functionality."""

    def test_write_summary(self, temp_dir, sample_results):
        """Test writing summary CSV."""
        csv_path = write_summary_csv(sample_results, base_path=temp_dir)
        
        assert Path(csv_path).exists()
        assert csv_path.endswith(".csv")
        assert "summary" in csv_path

    def test_summary_filename_format(self, temp_dir, sample_results):
        """Test that summary filename follows expected pattern."""
        csv_path = write_summary_csv(sample_results, base_path=temp_dir)
        filename = Path(csv_path).name
        
        assert filename.startswith("scan_summary_")
        assert filename.endswith(".csv")

    def test_summary_sorting(self, temp_dir, sample_results):
        """Test that summary is sorted by total_score descending."""
        csv_path = write_summary_csv(sample_results, base_path=temp_dir)
        df = pd.read_csv(csv_path)
        
        # First row should be AAPL (higher score)
        assert df.iloc[0]["ticker"] == "AAPL.US"
        assert df.iloc[1]["ticker"] == "TSLA.US"

    def test_summary_contains_key_metrics(self, temp_dir, sample_results):
        """Test that summary contains all key metrics."""
        csv_path = write_summary_csv(sample_results, base_path=temp_dir)
        df = pd.read_csv(csv_path)
        
        required_cols = [
            "ticker",
            "total_score",
            "triggered_signal_count",
            "timeframes_with_signals",
            "data_source",
        ]
        for col in required_cols:
            assert col in df.columns


class TestLoadScanResultsFromCsv:
    """Test loading scan results from CSV."""

    def test_load_csv(self, temp_dir, sample_results):
        """Test loading results from CSV."""
        csv_path = write_scan_results_to_csv(sample_results, base_path=temp_dir)
        df = load_scan_results_from_csv(csv_path)
        
        assert len(df) == 2
        assert "ticker" in df.columns
        assert "total_score" in df.columns

    def test_loaded_data_integrity(self, temp_dir, sample_results):
        """Test that loaded data matches original data."""
        csv_path = write_scan_results_to_csv(sample_results, base_path=temp_dir)
        df = load_scan_results_from_csv(csv_path)
        
        # Check that tickers match
        assert set(df["ticker"]) == {"AAPL.US", "TSLA.US"}
        
        # Check scores
        aapl_row = df[df["ticker"] == "AAPL.US"].iloc[0]
        assert aapl_row["total_score"] == 100.5
