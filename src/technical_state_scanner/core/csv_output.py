"""Reusable report output helpers for scanner results."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pandas as pd

from technical_state_scanner.core.scanner import (
    LightweightUniverseResult,
    ScanResult,
    scan_results_to_dataframe,
)


TIMEFRAME_OUTPUT_NAMES = {
    "weekly": "weekly",
    "daily": "daily",
    "4hour": "four_hour",
    "4h": "four_hour",
}


def ensure_reports_directory(base_path: str = ".") -> Path:
    """Ensure the reports directory exists.
    
    Args:
        base_path: Base path for the reports directory (default: current directory)
        
    Returns:
        Path to the reports directory
    """
    reports_dir = Path(base_path) / "reports"
    reports_dir.mkdir(parents=True, exist_ok=True)
    return reports_dir


def write_scan_results_to_csv(
    results: list[ScanResult],
    output_path: str | None = None,
    base_path: str = ".",
) -> str:
    """Write scan results to a CSV file.
    
    Args:
        results: List of ScanResult to write
        output_path: Optional specific output file path (default: auto-generated in reports/)
        base_path: Base path for reports directory if output_path not specified
        
    Returns:
        Path to the written CSV file
    """
    # Ensure reports directory exists
    reports_dir = ensure_reports_directory(base_path)

    # Determine output path
    if output_path:
        csv_path = Path(output_path)
        csv_path.parent.mkdir(parents=True, exist_ok=True)
    else:
        # Generate timestamp-based filename
        from datetime import datetime
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        csv_path = reports_dir / f"scan_results_{timestamp}.csv"

    # Convert results to DataFrame
    df = scan_results_to_dataframe(results)

    # Write to CSV
    df.to_csv(csv_path, index=False)
    return str(csv_path)


def _join_values(values: list[Any] | tuple[Any, ...] | set[Any] | None) -> str:
    if not values:
        return "None"
    return ";".join(str(value) for value in values)


def _json_text(value: Any) -> str:
    return json.dumps(value, sort_keys=True, default=str)


def lightweight_universe_results_to_dataframe(
    results: list[LightweightUniverseResult],
) -> pd.DataFrame:
    """Convert lightweight universe scan results to CSV-ready rows.

    The output keeps only data fields needed for ranked universe browsing. It does
    not include chart data, chart images, or full factor diagnostic details.
    """

    rows: list[dict[str, Any]] = []
    for result in results:
        scores = result.scores or {}
        row: dict[str, Any] = {
            "ticker": result.ticker,
            "total_score": scores.get("total_score", 0.0),
            "pre_multiplier_score": scores.get("pre_multiplier_score", 0.0),
            "cross_timeframe_all_factor_coverage_multiplier": scores.get(
                "cross_timeframe_all_factor_coverage_multiplier", 1.0
            ),
            "all_triggered_signals": _join_values(result.triggered_signals),
            "factor_confluence_summary": _json_text(result.factor_confluence),
            "data_source": result.data_source,
            "timestamps": _json_text(result.timestamps),
            "failed_reason": result.error or "None",
        }

        base_scores = scores.get("base_timeframe_scores", {})
        for internal_name, output_name in TIMEFRAME_OUTPUT_NAMES.items():
            if internal_name == "4h":
                continue
            confluence = result.factor_confluence.get(internal_name, {})
            timeframe_signals = result.timeframe_triggered_signals.get(internal_name, [])
            timeframe_factors = result.timeframe_triggered_factors.get(internal_name, [])
            row[f"{output_name}_triggered_signals"] = _join_values(timeframe_signals)
            row[f"{output_name}_triggered_factors"] = _join_values(timeframe_factors)
            row[f"{output_name}_score"] = confluence.get("score", 0)

        row["base_timeframe_scores"] = _json_text(base_scores)
        rows.append(row)

    return pd.DataFrame(rows)


def write_universe_results_to_csv(
    results: list[LightweightUniverseResult],
    output_path: str | None = None,
    base_path: str = ".",
) -> str:
    """Write lightweight universe scan results to ``reports/`` as CSV."""

    reports_dir = ensure_reports_directory(base_path)
    if output_path:
        csv_path = Path(output_path)
        csv_path.parent.mkdir(parents=True, exist_ok=True)
    else:
        from datetime import datetime

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        csv_path = reports_dir / f"universe_scan_{timestamp}.csv"

    df = lightweight_universe_results_to_dataframe(results)
    df.to_csv(csv_path, index=False)
    return str(csv_path)


def _extract_single_result_timestamps(result: ScanResult) -> dict[str, dict[str, str | None]]:
    timestamps: dict[str, dict[str, str | None]] = {}
    for timeframe, timeframe_result in result.timeframe_results.items():
        timestamps[timeframe] = {}
        for factor_id, factor_result in timeframe_result.get("details", {}).items():
            timestamps[timeframe][factor_id] = factor_result.get("timestamp")
    return timestamps


def scan_result_to_structured_output(result: ScanResult) -> dict[str, Any]:
    """Return nested JSON-like output for a detailed single-stock scan."""

    return {
        "ticker": result.ticker,
        "total_score": result.total_score,
        "scoring_breakdown": {
            "base_timeframe_scores": result.base_timeframe_scores,
            "factor_confluence_scores": result.factor_confluence_scores,
            "cross_timeframe_all_factor_coverage_multiplier": (
                result.cross_timeframe_all_factor_coverage_multiplier
            ),
            "pre_multiplier_score": result.pre_multiplier_score,
            "total_score": result.total_score,
        },
        "all_triggered_signals": result.all_triggered_signals,
        "timeframes": result.timeframe_results,
        "factor_confluence": result.factor_confluence_scores,
        "data_source": result.data_source,
        "timestamps": _extract_single_result_timestamps(result),
        "failed_reason": result.error,
        "notes": result.notes,
    }


def write_single_scan_result_to_json(
    result: ScanResult,
    output_path: str | None = None,
    base_path: str = ".",
) -> str:
    """Write a detailed single-stock scan result as structured JSON data."""

    reports_dir = ensure_reports_directory(base_path)
    if output_path:
        json_path = Path(output_path)
        json_path.parent.mkdir(parents=True, exist_ok=True)
    else:
        from datetime import datetime

        safe_ticker = result.ticker.replace(".", "_")
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        json_path = reports_dir / f"{safe_ticker}_scan_{timestamp}.json"

    payload = scan_result_to_structured_output(result)
    json_path.write_text(json.dumps(payload, indent=2, sort_keys=True, default=str), encoding="utf-8")
    return str(json_path)


def write_summary_csv(
    results: list[ScanResult],
    output_path: str | None = None,
    base_path: str = ".",
) -> str:
    """Write a summary CSV with key metrics only.
    
    Args:
        results: List of ScanResult to summarize
        output_path: Optional specific output file path
        base_path: Base path for reports directory if output_path not specified
        
    Returns:
        Path to the written CSV file
    """
    # Ensure reports directory exists
    reports_dir = ensure_reports_directory(base_path)

    # Determine output path
    if output_path:
        csv_path = Path(output_path)
        csv_path.parent.mkdir(parents=True, exist_ok=True)
    else:
        from datetime import datetime
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        csv_path = reports_dir / f"scan_summary_{timestamp}.csv"

    # Create summary DataFrame with key metrics
    rows = []
    for result in results:
        triggered_count = len(set(result.all_triggered_signals))
        timeframes_with_signals = sum(
            1 for tf in result.timeframe_results.values()
            if tf.get("triggered_signals")
        )

        row = {
            "ticker": result.ticker,
            "total_score": f"{result.total_score:.1f}",
            "pre_multiplier_score": f"{result.pre_multiplier_score:.1f}",
            "coverage_multiplier": result.cross_timeframe_all_factor_coverage_multiplier,
            "triggered_signal_count": triggered_count,
            "timeframes_with_signals": timeframes_with_signals,
            "all_signals": ";".join(result.all_triggered_signals) or "None",
            "data_source": result.data_source,
            "error": result.error or "None",
        }
        rows.append(row)

    summary_df = pd.DataFrame(rows)

    # Sort by total_score descending for easy scanning
    # Convert back to float for sorting, then back to string
    summary_df["total_score_float"] = summary_df["total_score"].astype(float)
    summary_df = summary_df.sort_values("total_score_float", ascending=False).drop("total_score_float", axis=1)

    # Write to CSV
    summary_df.to_csv(csv_path, index=False)
    return str(csv_path)


def load_scan_results_from_csv(csv_path: str) -> pd.DataFrame:
    """Load scan results from a previously written CSV file.
    
    Args:
        csv_path: Path to the CSV file
        
    Returns:
        pandas DataFrame with scan results
    """
    return pd.read_csv(csv_path)
