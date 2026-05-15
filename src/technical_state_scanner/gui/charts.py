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
CHART_WINDOWS_DAYS = [5, 10, 15, 20, 30, 100, 200]


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

    signals = timeframe_result.get("triggered_signals", [])
    return signals or []


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


def slice_recent_chart_window(frame: pd.DataFrame | None, days: int, min_rows: int | None = None) -> pd.DataFrame:
    """Return recent rows while keeping sparse timeframes readable."""

    if frame is None or frame.empty:
        return pd.DataFrame()
    sorted_frame = frame.sort_index()
    if not isinstance(sorted_frame.index, pd.DatetimeIndex):
        row_count = max(days, min_rows or 0)
        return sorted_frame.tail(row_count).copy()
    latest = sorted_frame.index.max()
    start = latest - pd.Timedelta(days=days)
    window = sorted_frame.loc[sorted_frame.index >= start].copy()
    if min_rows is not None and len(window) < min_rows:
        return sorted_frame.tail(min_rows).copy()
    return window if not window.empty else sorted_frame.tail(1).copy()


def minimum_visible_rows_for_timeframe(timeframe_key: str) -> int:
    """Return enough bars for each timeframe to fill the chart area usefully."""

    if timeframe_key == "weekly":
        return 52
    if timeframe_key == "daily":
        return 120
    if timeframe_key == "4hour":
        return 120
    return 60


def candle_width_for_timeframe(timeframe_key: str) -> float:
    """Return readable candle body width for finplot's x-indexed candles."""

    if timeframe_key == "weekly":
        return 0.92
    if timeframe_key == "daily":
        return 0.72
    if timeframe_key == "4hour":
        return 0.58
    return 0.65


def x_bounds_for_timeframe(timeframe_key: str, chart_data: pd.DataFrame) -> tuple[Any, Any]:
    """Return x-axis bounds for the visible chart window."""

    if chart_data.empty:
        return 0, 0
    if timeframe_key in {"4hour", "daily", "weekly"}:
        return 0, len(chart_data) - 1
    return chart_data.index[0], chart_data.index[-1]


def prepare_finplot_ohlc_data(
    frame: pd.DataFrame | None,
    days: int,
    timeframe_key: str | None = None,
) -> pd.DataFrame:
    """Return OHLC plus available overlay columns for finplot rendering."""

    min_rows = minimum_visible_rows_for_timeframe(timeframe_key) if timeframe_key else None
    chart_frame = slice_recent_chart_window(frame, days, min_rows=min_rows)
    if chart_frame.empty:
        return pd.DataFrame()
    required = ["Open", "High", "Low", "Close"]
    if any(column not in chart_frame.columns for column in required):
        return pd.DataFrame()
    columns = required.copy()
    columns.extend(column for column in EMA_COLUMNS + VEGAS_COLUMNS if column in chart_frame.columns)
    return chart_frame[columns].dropna(subset=required).copy()


def prepare_ema_overlay_data(chart_data: pd.DataFrame) -> dict[str, pd.Series]:
    """Return clean EMA series for explicit finplot overlay rendering."""

    overlays: dict[str, pd.Series] = {}
    for column in EMA_COLUMNS:
        if column not in chart_data.columns:
            continue
        series = pd.to_numeric(chart_data[column], errors="coerce").dropna()
        if not series.empty:
            overlays[column] = series
    return overlays


def prepare_volume_panel_data(frame: pd.DataFrame | None, max_rows: int = 350) -> pd.DataFrame:
    """Return volume data for the selected timeframe."""

    if frame is None or frame.empty or "Volume" not in frame.columns:
        return pd.DataFrame()
    return frame[["Volume"]].tail(max_rows).copy()


def get_triggered_factor_labels(timeframe_result: dict[str, Any]) -> list[str]:
    """Return labels for triggered factors in the selected timeframe."""

    signals = timeframe_result.get("triggered_signals", [])
    return signals or []
