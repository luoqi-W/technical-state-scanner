from __future__ import annotations

from typing import Any

import pandas as pd

from technical_state_scanner.core.csv_output import lightweight_universe_results_to_dataframe
from technical_state_scanner.core.scanner import (
    LightweightUniverseResult,
    ScanResult,
    load_named_universe,
    load_symbols_from_file,
    scan_symbol,
    scan_universe_lightweight,
)
from technical_state_scanner.gui.charts import (
    build_factor_combination_summary,
    build_status_sentence,
    build_timeframe_explanation,
    make_badges_html,
    summarize_confluence_map,
    summarize_timestamps,
)
from technical_state_scanner.loader import load_multi_timeframe_ohlcv, normalize_symbol


TIMEFRAME_OPTIONS = {
    "4H": "4hour",
    "Daily": "daily",
    "Weekly": "weekly",
}
EMA_COLUMNS = ["EMA12", "EMA144", "EMA169", "EMA576", "EMA676"]
VEGAS_COLUMNS = ["VegasLower", "VegasUpper"]


def get_timeframe_key(label: str) -> str:
    """Map UI timeframe labels to scanner timeframe keys."""

    return TIMEFRAME_OPTIONS[label]


def format_signal_list(values: list[str] | None) -> str:
    """Format signal/factor lists for compact UI display."""

    if not values:
        return "None"
    return ", ".join(values)


def make_score_summary(result: ScanResult) -> dict[str, Any]:
    """Build the persistent score summary shown above timeframe details."""

    return {
        "ticker": result.ticker,
        "total_score": result.total_score,
        "pre_multiplier_score": result.pre_multiplier_score,
        "cross_timeframe_all_factor_coverage_multiplier": (
            result.cross_timeframe_all_factor_coverage_multiplier
        ),
        "all_triggered_signals": result.all_triggered_signals,
        "base_timeframe_scores": result.base_timeframe_scores,
        "factor_confluence_scores": result.factor_confluence_scores,
        "data_source": result.data_source,
        "failed_reason": result.error,
    }


def make_universe_table(results: list[LightweightUniverseResult]) -> pd.DataFrame:
    """Return a ranked lightweight universe table for Streamlit display."""

    rows = []
    for result in results:
        rows.append(
            {
                "Ticker": result.ticker,
                "Total Score": result.scores.get("total_score", 0.0),
                "Triggered Signals": format_signal_list(result.triggered_signals),
                "Triggered Factors": format_signal_list(result.triggered_factors),
                "Factor Combination": summarize_confluence_map(result.factor_confluence),
                "Latest Signal Time": summarize_timestamps(result.timestamps),
                "Failed Reason": result.error or "None",
            }
        )
    if not rows:
        return pd.DataFrame()
    return pd.DataFrame(rows).sort_values("Total Score", ascending=False)


def prepare_chart_data(frame: pd.DataFrame, max_rows: int = 220) -> pd.DataFrame:
    """Prepare OHLCV and indicator columns for a selected timeframe chart."""

    if frame.empty:
        return pd.DataFrame()

    columns = ["Open", "High", "Low", "Close"]
    columns.extend(column for column in EMA_COLUMNS + VEGAS_COLUMNS if column in frame.columns)
    chart_df = frame[columns].tail(max_rows).copy()
    chart_df = chart_df.reset_index()
    index_name = chart_df.columns[0]
    chart_df = chart_df.rename(columns={index_name: "Datetime"})
    chart_df["Datetime"] = pd.to_datetime(chart_df["Datetime"]).astype(str)
    chart_df["is_up"] = chart_df["Close"] >= chart_df["Open"]
    return chart_df


def build_candlestick_vega_spec(chart_data: pd.DataFrame) -> dict[str, Any]:
    """Build a Vega-Lite candlestick + EMA overlay spec without figure objects."""

    indicator_columns = [
        column for column in EMA_COLUMNS + VEGAS_COLUMNS if column in chart_data.columns
    ]
    layers: list[dict[str, Any]] = [
        {
            "mark": {"type": "rule"},
            "encoding": {
                "x": {"field": "Datetime", "type": "temporal", "title": None},
                "y": {"field": "Low", "type": "quantitative", "title": "Price"},
                "y2": {"field": "High"},
                "color": {
                    "condition": {"test": "datum.is_up", "value": "#0f8b6f"},
                    "value": "#c0392b",
                },
            },
        },
        {
            "mark": {"type": "bar", "size": 5},
            "encoding": {
                "x": {"field": "Datetime", "type": "temporal", "title": None},
                "y": {"field": "Open", "type": "quantitative"},
                "y2": {"field": "Close"},
                "color": {
                    "condition": {"test": "datum.is_up", "value": "#0f8b6f"},
                    "value": "#c0392b",
                },
            },
        },
    ]

    for column in indicator_columns:
        layers.append(
            {
                "mark": {"type": "line", "strokeWidth": 1.3},
                "encoding": {
                    "x": {"field": "Datetime", "type": "temporal", "title": None},
                    "y": {"field": column, "type": "quantitative", "title": "Price"},
                    "color": {"datum": column, "type": "nominal", "title": "Line"},
                },
            }
        )

    return {
        "height": 460,
        "resolve": {"scale": {"y": "shared"}},
        "layer": layers,
    }


def get_timeframe_result(result: ScanResult, timeframe_key: str) -> dict[str, Any]:
    """Return timeframe details with a safe empty fallback."""

    return result.timeframe_results.get(
        timeframe_key,
        {
            "triggered_signals": [],
            "triggered_factors": [],
            "factor_confluence_tier": None,
            "factor_confluence_score": 0,
            "details": {},
        },
    )


def _render_score_summary(st: Any, result: ScanResult) -> None:
    summary = make_score_summary(result)
    st.subheader("Scan Result")
    cols = st.columns(3)
    cols[0].metric("Ticker", summary["ticker"])
    cols[1].metric("Total Score", f"{summary['total_score']:.1f}")
    cols[2].metric("Data Source", "LongPort OpenAPI")
    st.caption("Data source: LongPort OpenAPI")
    if summary["failed_reason"]:
        st.error(f"Failed Reason: {summary['failed_reason']}")
    st.markdown("**Triggered Signals**")
    st.markdown(make_badges_html(summary["all_triggered_signals"]), unsafe_allow_html=True)
    with st.expander("Advanced scoring details", expanded=False):
        st.write("These fields are shown for debugging and verification only.")
        st.write(f"Pre-multiplier score: {summary['pre_multiplier_score']:.1f}")
        st.write(
            "Cross-timeframe coverage multiplier: "
            f"{summary['cross_timeframe_all_factor_coverage_multiplier']}"
        )
        st.write("Base timeframe scores")
        st.json(summary["base_timeframe_scores"])
        st.write("Factor confluence scores")
        st.json(summary["factor_confluence_scores"])


def _render_timeframe_selector(st: Any, state_key: str) -> str:
    if state_key not in st.session_state:
        st.session_state[state_key] = "Daily"
    cols = st.columns(3)
    for idx, label in enumerate(["4H", "Daily", "Weekly"]):
        button_type = "primary" if st.session_state[state_key] == label else "secondary"
        if cols[idx].button(label, key=f"{state_key}_{label}", type=button_type, use_container_width=True):
            st.session_state[state_key] = label
    return st.session_state[state_key]


def _load_selected_chart_data(symbol: str, timeframe_key: str, count: int) -> pd.DataFrame:
    frames, _statuses = load_multi_timeframe_ohlcv(symbol=symbol, count=count)
    return frames.get(timeframe_key, pd.DataFrame())


def _render_selected_timeframe(st: Any, result: ScanResult, selected_label: str, count: int) -> None:
    timeframe_key = get_timeframe_key(selected_label)
    timeframe_result = get_timeframe_result(result, timeframe_key)

    left, right = st.columns([2, 1])
    with left:
        st.subheader(f"{selected_label} Chart")
        try:
            frame = _load_selected_chart_data(result.ticker, timeframe_key, count=count)
            chart_data = prepare_chart_data(frame)
            if chart_data.empty:
                st.warning("No chart data available for this timeframe.")
            else:
                st.vega_lite_chart(chart_data, build_candlestick_vega_spec(chart_data), use_container_width=True)
        except Exception as exc:
            st.error(f"Unable to load selected timeframe chart data: {exc}")

    with right:
        st.subheader("Timeframe Result")
        st.write(f"Selected Timeframe: {selected_label}")
        st.markdown("**Status**")
        st.write(build_status_sentence(result, selected_label, timeframe_result))
        st.markdown("**Triggered Factors**")
        st.markdown(
            make_badges_html(timeframe_result.get("triggered_factors", []), "No triggered factors"),
            unsafe_allow_html=True,
        )
        st.markdown("**Triggered Signals**")
        st.markdown(
            make_badges_html(timeframe_result.get("triggered_signals", []), "No triggered signals"),
            unsafe_allow_html=True,
        )
        st.markdown("**Factor Combination**")
        st.write(build_factor_combination_summary(selected_label, timeframe_result))
        st.markdown("**Short Explanation**")
        for line in build_timeframe_explanation(selected_label, timeframe_result):
            st.write(f"- {line}")
        with st.expander("Advanced factor diagnostics", expanded=False):
            st.write("Matched rule")
            st.write(result.factor_confluence_scores.get(timeframe_key, {}).get("matched_rule") or "None")
            st.json(timeframe_result.get("details", {}))
        with st.expander("Raw debug data", expanded=False):
            st.json(
                {
                    "timeframe": timeframe_key,
                    "triggered_factors": timeframe_result.get("triggered_factors", []),
                    "triggered_signals": timeframe_result.get("triggered_signals", []),
                    "factor_confluence": result.factor_confluence_scores.get(timeframe_key, {}),
                }
            )


def _parse_watchlist_text(text: str) -> list[str]:
    symbols: list[str] = []
    for line in text.splitlines():
        symbol = line.strip()
        if symbol and not symbol.startswith("#"):
            normalized = normalize_symbol(symbol)
            if normalized not in symbols:
                symbols.append(normalized)
    return symbols


def _render_single_scan_tab(st: Any) -> None:
    ticker = st.text_input("Ticker", value="AAPL", key="single_ticker")
    count = st.number_input("Candles per timeframe", min_value=100, max_value=2000, value=700, step=50)
    if st.button("Scan", type="primary", key="single_scan_button"):
        st.session_state["single_scan_result"] = scan_symbol(ticker, count=int(count))

    result = st.session_state.get("single_scan_result")
    if result:
        _render_score_summary(st, result)
        selected_label = _render_timeframe_selector(st, "single_timeframe")
        _render_selected_timeframe(st, result, selected_label, count=int(count))


def _render_universe_tab(st: Any) -> None:
    st.subheader("Universe Scan")
    source = st.radio("Universe Source", ["Custom list", "CSV/TXT file path", "Named local universe"], horizontal=True)
    count = st.number_input("Universe candles per timeframe", min_value=100, max_value=2000, value=700, step=50)

    symbols: list[str] = []
    if source == "Custom list":
        text = st.text_area("Symbols", value="AAPL\nTSLA\nMSFT", height=100)
        symbols = _parse_watchlist_text(text)
    elif source == "CSV/TXT file path":
        path = st.text_input("Universe file path", value="data/universes/my_watchlist.csv")
        column = st.text_input("CSV symbol column (optional)", value="")
        if path:
            try:
                symbols = load_symbols_from_file(path, symbol_column=column or None)
            except Exception as exc:
                st.warning(str(exc))
    else:
        universe = st.selectbox("Named universe", ["sp500", "nasdaq"])
        try:
            symbols = load_named_universe(universe)
        except Exception as exc:
            st.warning(str(exc))

    if st.button("Scan Universe", type="primary", key="universe_scan_button"):
        if symbols:
            st.session_state["universe_results"] = scan_universe_lightweight(symbols, count=int(count))
        else:
            st.warning("No symbols available to scan.")

    results = st.session_state.get("universe_results", [])
    if results:
        table = make_universe_table(results)
        st.dataframe(table, hide_index=True, use_container_width=True)
        selected_ticker = st.selectbox("Select ticker for lazy chart rendering", table["Ticker"].tolist())
        selected_result = next((item for item in results if item.ticker == selected_ticker), None)
        if selected_result is not None:
            detailed_result = st.session_state.get(f"detail_{selected_ticker}")
            if detailed_result is None or st.button("Refresh Selected Ticker Detail", key=f"refresh_{selected_ticker}"):
                detailed_result = scan_symbol(selected_ticker, count=int(count))
                st.session_state[f"detail_{selected_ticker}"] = detailed_result
            _render_score_summary(st, detailed_result)
            selected_label = _render_timeframe_selector(st, "universe_timeframe")
            _render_selected_timeframe(st, detailed_result, selected_label, count=int(count))


def run_app() -> None:
    import streamlit as st

    st.set_page_config(page_title="Technical State Scanner", layout="wide")
    st.title("Technical State Scanner")
    st.caption("LongPort OpenAPI data source. Signals are independent; no factor priority is applied.")

    single_tab, universe_tab = st.tabs(["Single Stock", "Universe"])
    with single_tab:
        _render_single_scan_tab(st)
    with universe_tab:
        _render_universe_tab(st)


if __name__ == "__main__":
    run_app()
