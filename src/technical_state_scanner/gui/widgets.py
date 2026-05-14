from __future__ import annotations

import json
from typing import Any

from technical_state_scanner.gui.charts import (
    build_factor_combination_summary,
    make_badges_html,
)


def get_dark_stylesheet() -> str:
    """Return the desktop GUI dark theme stylesheet."""

    return """
    QWidget {
        background: #101418;
        color: #d8dee9;
        font-family: Segoe UI, Arial, sans-serif;
        font-size: 12px;
    }
    QFrame#SummaryPanel, QFrame#ChartPanel {
        background: #161b22;
        border: 1px solid #2b333d;
        border-radius: 6px;
    }
    QFrame#Card {
        background: #0d1117;
        border: 1px solid #30363d;
        border-radius: 6px;
        padding: 8px;
    }
    QLabel#Title {
        color: #ffffff;
        font-size: 18px;
        font-weight: 700;
    }
    QLabel#Muted {
        color: #8b949e;
    }
    QLabel#Score {
        color: #58a6ff;
        font-size: 26px;
        font-weight: 700;
    }
    QLabel#Warning {
        color: #f2cc60;
    }
    QLineEdit, QSpinBox, QComboBox {
        background: #0d1117;
        border: 1px solid #30363d;
        border-radius: 4px;
        padding: 5px 8px;
        color: #f0f6fc;
    }
    QPushButton {
        background: #238636;
        border: 1px solid #2ea043;
        border-radius: 4px;
        color: #ffffff;
        padding: 6px 12px;
        font-weight: 600;
    }
    QPushButton:hover {
        background: #2ea043;
    }
    QPushButton:disabled {
        background: #30363d;
        border-color: #30363d;
        color: #8b949e;
    }
    QRadioButton {
        spacing: 6px;
    }
    QTableWidget {
        background: #0d1117;
        border: 1px solid #30363d;
        gridline-color: #30363d;
        color: #d8dee9;
    }
    QHeaderView::section {
        background: #161b22;
        color: #d8dee9;
        border: 1px solid #30363d;
        padding: 4px;
    }
    """


def format_summary_html(summary: dict[str, Any]) -> str:
    """Format summary data as compact rich text for QLabel."""

    close = summary.get("latest_close")
    close_text = "N/A" if close is None else f"{close:.2f}"
    confluence = summary.get("selected_timeframe_factor_confluence", {})
    failed_reason = summary.get("failed_reason")
    warning_html = ""
    if failed_reason:
        warning_html = f"<p style='color:#f85149;'><b>Failed:</b> {failed_reason}</p>"

    return f"""
    <div>
      <p style='color:#8b949e;margin-bottom:2px;'>Ticker</p>
      <h2 style='margin-top:0;color:#ffffff;'>{summary.get('ticker', 'N/A')}</h2>
      <p style='color:#8b949e;'><b>Latest:</b> {summary.get('latest_date', 'N/A')} | Close {close_text}</p>
      <p style='color:#58a6ff;font-size:24px;font-weight:700;margin:8px 0;'>
        Total Score: {summary.get('total_score', 0.0):.1f}
      </p>
      <p><b>Status</b><br>{summary.get('status', 'No scan result yet.')}</p>
      <p><b>Triggered Signals</b><br>{make_badges_html(summary.get('all_triggered_signals', []))}</p>
      <hr>
      <p><b>Timeframe</b><br>{summary.get('active_timeframe', 'N/A')}</p>
      <p><b>Triggered Factors</b><br>{make_badges_html(summary.get('selected_timeframe_triggered_factors', []), 'No triggered factors')}</p>
      <p><b>Factor Combination</b><br>{confluence.get('tier') or 'None'}</p>
      <p style='color:#8b949e;'><b>Data source:</b> {summary.get('data_source', 'LongPort OpenAPI')}</p>
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

    factors = timeframe_result.get("triggered_factors", [])
    lines = [
        f"Selected Timeframe: {timeframe_label}",
        "",
        "Triggered Factors:",
    ]
    if factors:
        lines.extend(f"- {factor}" for factor in factors)
    else:
        lines.append("- None")
    lines.extend(["", "Short Explanation:"])
    lines.extend(f"- {line}" for line in build_timeframe_explanation(timeframe_label, timeframe_result))
    lines.extend(
        [
            "",
            "Factor Combination:",
            f"- {build_factor_combination_summary(timeframe_label, timeframe_result)}",
        ]
    )
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
