from __future__ import annotations

from typing import Any

import pandas as pd

from technical_state_scanner.core.scanner import ScanResult


TIMEFRAME_LABEL_TO_KEY = {
    "4H": "4hour",
    "Daily": "daily",
    "Weekly": "weekly",
}
EMA_COLUMNS = ["EMA12", "EMA144", "EMA169", "EMA576", "EMA676"]
VEGAS_COLUMNS = ["VegasLower", "VegasUpper"]


def get_timeframe_key(label: str) -> str:
    """Map desktop GUI timeframe labels to scanner timeframe keys."""

    return TIMEFRAME_LABEL_TO_KEY[label]


def format_list(values: list[str] | None) -> str:
    """Return a compact user-facing string for signal/factor lists."""

    if not values:
        return "None"
    return ", ".join(values)


def format_badges(values: list[str] | None) -> list[str]:
    """Return clean badge labels for triggered signals or factors."""

    return values or []


def build_signal_pairs(timeframe_result: dict[str, Any]) -> list[str]:
    """Return readable factor + signal labels for the selected timeframe."""

    factors = timeframe_result.get("triggered_factors", [])
    signals = timeframe_result.get("triggered_signals", [])
    if not factors:
        return []
    labels: list[str] = []
    for index, factor in enumerate(factors):
        signal = signals[index] if index < len(signals) else factor
        labels.append(f"{factor} {signal}")
    return labels


def build_factor_combination_summary(timeframe_label: str, timeframe_result: dict[str, Any]) -> str:
    """Return a plain-language factor-combination summary."""

    tier = timeframe_result.get("factor_confluence_tier")
    if not tier:
        return "None"
    return f"{tier} pattern detected on {timeframe_label}"


def summarize_confluence_map(confluence_by_timeframe: dict[str, Any]) -> str:
    """Summarize confluence tiers across timeframes without raw dict output."""

    labels = []
    display_names = {"4hour": "4H", "daily": "Daily", "weekly": "Weekly"}
    for timeframe, data in confluence_by_timeframe.items():
        if isinstance(data, dict) and data.get("tier"):
            labels.append(f"{display_names.get(timeframe, timeframe)} {data['tier']}")
    return ", ".join(labels) if labels else "None"


def summarize_timestamps(timestamps: dict[str, Any]) -> str:
    """Return the latest available timestamp from nested signal timestamps."""

    values: list[str] = []
    for timeframe_data in timestamps.values():
        if isinstance(timeframe_data, dict):
            values.extend(str(value) for value in timeframe_data.values() if value)
    return max(values) if values else "N/A"


def build_status_sentence(
    result: ScanResult | None,
    timeframe_label: str,
    timeframe_result: dict[str, Any],
) -> str:
    """Return a short beginner-friendly scan status sentence."""

    if result is None:
        return "Enter a ticker and scan to view results."
    if result.error:
        return "Scan failed. See the failed reason below."

    signals = timeframe_result.get("triggered_signals", [])
    if signals:
        return f"{timeframe_label} {format_list(signals)} detected."
    if result.all_triggered_signals:
        return "Signals were detected on another timeframe. This timeframe has no active signal."
    return "No triggered signals were detected across the scanned timeframes."


def build_timeframe_explanation(timeframe_label: str, timeframe_result: dict[str, Any]) -> list[str]:
    """Return concise selected-timeframe explanation bullets."""

    pairs = build_signal_pairs(timeframe_result)
    if not pairs:
        return [f"No triggered factors on {timeframe_label} timeframe."]
    return [
        f"{label} detected on {timeframe_label} timeframe."
        for label in pairs
    ] + ["This contributed to the final score."]


def make_badges_html(values: list[str] | None, empty_text: str = "No triggered signals") -> str:
    """Render signal/factor labels as compact HTML badges."""

    badges = format_badges(values)
    if not badges:
        return f"<span style='color:#8b949e;'>{empty_text}</span>"
    return " ".join(
        "<span style='display:inline-block;background:#1f6feb;color:#ffffff;"
        "border-radius:10px;padding:2px 8px;margin:2px;font-size:12px;'>"
        f"{badge}</span>"
        for badge in badges
    )


def get_timeframe_result(result: ScanResult | None, timeframe_key: str) -> dict[str, Any]:
    """Return selected timeframe result with a stable empty fallback."""

    if result is None:
        return _empty_timeframe_result()
    return result.timeframe_results.get(timeframe_key, _empty_timeframe_result())


def _empty_timeframe_result() -> dict[str, Any]:
    return {
        "triggered_signals": [],
        "triggered_factors": [],
        "factor_confluence_tier": None,
        "factor_confluence_score": 0,
        "details": {},
    }


def get_latest_snapshot(frame: pd.DataFrame | None) -> dict[str, Any]:
    """Extract latest date and close from a selected OHLCV frame."""

    if frame is None or frame.empty:
        return {"latest_date": "N/A", "latest_close": None}
    latest_ts = frame.index[-1]
    latest_close = float(frame["Close"].iloc[-1]) if "Close" in frame.columns else None
    return {
        "latest_date": latest_ts.isoformat() if hasattr(latest_ts, "isoformat") else str(latest_ts),
        "latest_close": latest_close,
    }


def build_summary_model(
    result: ScanResult | None,
    frames: dict[str, pd.DataFrame],
    timeframe_key: str,
) -> dict[str, Any]:
    """Build the persistent left-panel summary for the selected timeframe."""

    timeframe_result = get_timeframe_result(result, timeframe_key)
    snapshot = get_latest_snapshot(frames.get(timeframe_key))
    if result is None:
        return {
            "ticker": "N/A",
            "latest_date": snapshot["latest_date"],
            "latest_close": snapshot["latest_close"],
            "total_score": 0.0,
            "pre_multiplier_score": 0.0,
            "cross_timeframe_all_factor_coverage_multiplier": 1.0,
            "all_triggered_signals": [],
            "active_timeframe": timeframe_key,
            "selected_timeframe_triggered_factors": [],
            "selected_timeframe_triggered_signals": [],
            "selected_timeframe_factor_confluence": {
                "tier": None,
                "score": 0,
                "matched_rule": None,
            },
            "data_source": "LongPort OpenAPI",
            "failed_reason": None,
            "status": "Enter a ticker and scan to view results.",
        }

    confluence = result.factor_confluence_scores.get(timeframe_key, {})
    timeframe_label = next(
        (label for label, key in TIMEFRAME_LABEL_TO_KEY.items() if key == timeframe_key),
        timeframe_key,
    )
    return {
        "ticker": result.ticker,
        "latest_date": snapshot["latest_date"],
        "latest_close": snapshot["latest_close"],
        "total_score": result.total_score,
        "pre_multiplier_score": result.pre_multiplier_score,
        "cross_timeframe_all_factor_coverage_multiplier": (
            result.cross_timeframe_all_factor_coverage_multiplier
        ),
        "all_triggered_signals": result.all_triggered_signals,
        "active_timeframe": timeframe_key,
        "selected_timeframe_triggered_factors": timeframe_result.get("triggered_factors", []),
        "selected_timeframe_triggered_signals": timeframe_result.get("triggered_signals", []),
        "selected_timeframe_factor_confluence": {
            "tier": timeframe_result.get("factor_confluence_tier"),
            "score": timeframe_result.get("factor_confluence_score", 0),
            "matched_rule": confluence.get("matched_rule"),
        },
        "data_source": result.data_source,
        "failed_reason": result.error,
        "status": build_status_sentence(result, timeframe_label, timeframe_result),
    }


def prepare_price_panel_data(frame: pd.DataFrame | None, max_rows: int = 350) -> pd.DataFrame:
    """Return only chartable price and indicator columns for pyqtgraph."""

    if frame is None or frame.empty:
        return pd.DataFrame()
    columns = ["Close"]
    columns.extend(column for column in EMA_COLUMNS + VEGAS_COLUMNS if column in frame.columns)
    return frame[columns].tail(max_rows).copy()


def prepare_volume_panel_data(frame: pd.DataFrame | None, max_rows: int = 350) -> pd.DataFrame:
    """Return volume data for the selected timeframe."""

    if frame is None or frame.empty or "Volume" not in frame.columns:
        return pd.DataFrame()
    return frame[["Volume"]].tail(max_rows).copy()


def get_triggered_factor_labels(timeframe_result: dict[str, Any]) -> list[str]:
    """Return labels for triggered factors in the selected timeframe."""

    factors = timeframe_result.get("triggered_factors", [])
    signals = timeframe_result.get("triggered_signals", [])
    return [f"{factor}: {signal}" for factor, signal in zip(factors, signals)]
