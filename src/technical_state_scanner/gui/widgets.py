from __future__ import annotations

import json
from typing import Any

from technical_state_scanner.gui.charts import (
    format_list,
)


def get_dark_stylesheet() -> str:
    """Return the desktop GUI dark theme stylesheet."""

    return """
    /* === Base === */
    QWidget {
        background: #0b0f14;
        color: #e6edf3;
        font-family: 'Segoe UI', 'SF Pro Display', Arial, sans-serif;
        font-size: 14px;
    }

    /* === Panels === */
    QFrame#SummaryPanel {
        background: #101720;
        border: 1px solid #263241;
        border-radius: 8px;
    }
    QFrame#ChartPanel {
        background: #101720;
        border: 1px solid #263241;
        border-radius: 8px;
    }
    QFrame#ScanBar {
        background: #121a24;
        border: 1px solid #2c3a4a;
        border-radius: 8px;
    }
    QFrame#TimeframePanel {
        background: transparent;
        border: none;
    }

    /* === Cards === */
    QFrame#FactorCard {
        background: #0d131b;
        border: 1px solid #2b3746;
        border-radius: 6px;
    }
    QFrame#FactorCardActive {
        background: #10243a;
        border: 2px solid #4aa3ff;
        border-radius: 6px;
    }
    QPushButton#TimeframeCardButton {
        background: #0d131b;
        border: 1px solid #2b3746;
        border-radius: 6px;
        color: #e6edf3;
        padding: 10px 12px;
        font-weight: 500;
        font-size: 13px;
        line-height: 1.35;
        text-align: left;
    }
    QPushButton#TimeframeCardButton:hover {
        background: #111b27;
        border-color: #4aa3ff;
    }
    QPushButton#TimeframeCardButton:checked {
        background: #10243a;
        border: 2px solid #4aa3ff;
        color: #ffffff;
    }

    /* === Typography === */
    QLabel#AppTitle {
        background: transparent;
        color: #ffffff;
        font-size: 20px;
        font-weight: 700;
    }
    QLabel#Title {
        background: transparent;
        color: #ffffff;
        font-size: 18px;
        font-weight: 700;
    }
    QLabel#SectionTitle {
        background: transparent;
        color: #e6edf3;
        font-size: 13px;
        font-weight: 600;
    }
    QLabel#Score {
        background: transparent;
        color: #58a6ff;
        font-size: 32px;
        font-weight: 700;
    }
    QLabel#Muted {
        background: transparent;
        color: #8b949e;
        font-size: 12px;
    }
    QLabel#Warning {
        background: transparent;
        color: #d29922;
    }

    QLabel {
        background: transparent;
    }

    /* === Inputs === */
    QLineEdit, QSpinBox, QComboBox {
        background: #08111a;
        border: 1px solid #314154;
        border-radius: 6px;
        padding: 7px 10px;
        color: #e6edf3;
        font-size: 13px;
        selection-background-color: #264f78;
    }
    QLineEdit:focus, QSpinBox:focus {
        border-color: #58a6ff;
    }
    QComboBox::drop-down {
        border: none;
        padding-right: 8px;
    }
    QComboBox QAbstractItemView {
        background: #121a24;
        border: 1px solid #314154;
        selection-background-color: #264f78;
        color: #e6edf3;
    }

    /* === Primary Button === */
    QPushButton#PrimaryButton {
        background: #238636;
        border: 1px solid #2ea043;
        border-radius: 6px;
        color: #ffffff;
        padding: 7px 16px;
        font-weight: 600;
        font-size: 13px;
    }
    QPushButton#PrimaryButton:hover {
        background: #2ea043;
        border-color: #3fb950;
    }
    QPushButton#PrimaryButton:pressed {
        background: #196c2e;
    }
    QPushButton#PrimaryButton:disabled {
        background: #21262d;
        border-color: #30363d;
        color: #484f58;
    }

    /* === Default Button === */
    QPushButton {
        background: #202a36;
        border: 1px solid #344356;
        border-radius: 6px;
        color: #e6edf3;
        padding: 7px 14px;
        font-weight: 600;
        font-size: 13px;
    }
    QPushButton:hover {
        background: #2c3847;
        border-color: #8b949e;
    }
    QPushButton:pressed {
        background: #17212c;
    }
    QPushButton:disabled {
        background: #161b22;
        border-color: #21262d;
        color: #484f58;
    }

    /* === Mode Toggle Buttons === */
    QPushButton#ModeButton {
        background: #21262d;
        border: 1px solid #30363d;
        border-radius: 6px;
        color: #8b949e;
        padding: 7px 20px;
        font-weight: 600;
    }
    QPushButton#ModeButton:checked {
        background: #0d419d;
        border-color: #58a6ff;
        color: #ffffff;
    }
    QPushButton#ModeButton:hover {
        border-color: #58a6ff;
        color: #e6edf3;
    }

    /* === Radio buttons === */
    QRadioButton {
        spacing: 6px;
        color: #e6edf3;
        padding: 3px 4px;
    }

    /* === Text areas === */
    QTextEdit {
        background: #08111a;
        border: 1px solid #263241;
        border-radius: 6px;
        color: #e6edf3;
        padding: 8px;
        font-family: 'Cascadia Code', 'Consolas', monospace;
        font-size: 12px;
    }
    QTextEdit#SideDetails {
        background: #0b1118;
        border: 1px solid #263241;
        color: #d8dee9;
        font-size: 12px;
    }

    /* === Table === */
    QTableWidget {
        background: #08111a;
        alternate-background-color: #0d151f;
        border: 1px solid #263241;
        border-radius: 6px;
        gridline-color: #1e2a36;
        color: #e6edf3;
        font-size: 12px;
        selection-background-color: #264f78;
    }
    QTableWidget::item {
        padding: 6px 8px;
        border-bottom: 1px solid #21262d;
    }
    QTableWidget::item:selected {
        background: #264f78;
        color: #ffffff;
    }
    QHeaderView::section {
        background: #121a24;
        color: #a9b4c0;
        border: none;
        border-bottom: 2px solid #314154;
        border-right: 1px solid #263241;
        padding: 8px;
        font-weight: 600;
        font-size: 12px;
    }

    /* === Progress bar === */
    QProgressBar {
        background: #21262d;
        border: none;
        border-radius: 3px;
        text-align: center;
        color: transparent;
    }
    QProgressBar::chunk {
        background: #58a6ff;
        border-radius: 3px;
    }

    /* === Splitter === */
    QSplitter::handle {
        background: #30363d;
        width: 1px;
    }
    QSplitter::handle:hover {
        background: #58a6ff;
    }

    /* === Scrollbar === */
    QScrollBar:vertical {
        background: transparent;
        width: 8px;
        border: none;
    }
    QScrollBar::handle:vertical {
        background: #30363d;
        border-radius: 4px;
        min-height: 20px;
    }
    QScrollBar::handle:vertical:hover {
        background: #484f58;
    }
    QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
        height: 0;
    }
    QScrollBar:horizontal {
        background: transparent;
        height: 8px;
        border: none;
    }
    QScrollBar::handle:horizontal {
        background: #30363d;
        border-radius: 4px;
        min-width: 20px;
    }
    QScrollBar::handle:horizontal:hover {
        background: #484f58;
    }
    QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {
        width: 0;
    }
    """


def _format_plain_signal_list(values: list[str] | None, empty_text: str = "No triggered signals") -> str:
    if not values:
        return f"<span style='color:#8b949e;'>{empty_text}</span>"
    return f"<span style='color:#e6edf3;'>{format_list(values)}</span>"


def format_summary_html(summary: dict[str, Any]) -> str:
    """Format summary data as compact rich text for QLabel."""

    close = summary.get("latest_close")
    close_text = "N/A" if close is None else f"{close:.2f}"
    failed_reason = summary.get("failed_reason")
    warning_html = ""
    if failed_reason:
        warning_html = f"<p style='color:#f85149;'><b>Failed:</b> {failed_reason}</p>"

    return f"""
    <div style='line-height:1.6;'>
      <p style='color:#8b949e;margin-bottom:2px;font-size:11px;text-transform:uppercase;letter-spacing:0.5px;'>Ticker</p>
      <h2 style='margin-top:0;color:#ffffff;font-size:22px;'>{summary.get('ticker', 'N/A')}</h2>
      <p style='color:#8b949e;font-size:12px;'><b>Latest:</b> {summary.get('latest_date', 'N/A')} | Close {close_text}</p>
      <p style='color:#58a6ff;font-size:28px;font-weight:700;margin:10px 0;'>
        Total Score: {summary.get('total_score', 0.0):.1f}
      </p>
      <p style='margin-top:8px;'><b>Status</b><br><span style='color:#e6edf3;'>{summary.get('status', 'No scan result yet.')}</span></p>
      <p><b>Triggered Signals</b><br>{_format_plain_signal_list(summary.get('all_triggered_signals', []))}</p>
      <hr style='border:none;border-top:1px solid #30363d;margin:12px 0;'>
      <p><b>Timeframe</b><br>{summary.get('active_timeframe', 'N/A')}</p>
      <p style='color:#8b949e;font-size:11px;margin-top:14px;'><b>Data source:</b> {summary.get('data_source', 'LongPort OpenAPI')}</p>
      {warning_html}
    </div>
    """


def format_advanced_summary_text(summary: dict[str, Any]) -> str:
    """Format backend scoring fields for an optional advanced desktop panel."""

    return json.dumps(
        {
            "pre_multiplier_score": summary.get("pre_multiplier_score"),
            "cross_timeframe_all_factor_coverage_multiplier": summary.get(
                "cross_timeframe_all_factor_coverage_multiplier"
            ),
            "selected_timeframe_factor_confluence": summary.get(
                "selected_timeframe_factor_confluence"
            ),
        },
        indent=2,
        sort_keys=True,
        default=str,
    )


def format_timeframe_summary_text(timeframe_label: str, timeframe_result: dict[str, Any]) -> str:
    """Format selected timeframe result without raw dictionaries."""

    from technical_state_scanner.gui.charts import build_timeframe_explanation

    signals = timeframe_result.get("triggered_signals", [])
    lines = [
        f"Selected Timeframe: {timeframe_label}",
        "",
        "Triggered Signals:",
    ]
    if signals:
        lines.extend(f"- {signal}" for signal in signals)
    else:
        lines.append("- None")
    lines.extend(["", "Short Explanation:"])
    lines.extend(f"- {line}" for line in build_timeframe_explanation(timeframe_label, timeframe_result))
    return "\n".join(lines)


def format_details_text(timeframe_result: dict[str, Any]) -> str:
    """Format selected timeframe details as readable JSON text."""

    return json.dumps(
        {
            "triggered_factors": timeframe_result.get("triggered_factors", []),
            "triggered_signals": timeframe_result.get("triggered_signals", []),
            "details": timeframe_result.get("details", {}),
        },
        indent=2,
        sort_keys=True,
        default=str,
    )
