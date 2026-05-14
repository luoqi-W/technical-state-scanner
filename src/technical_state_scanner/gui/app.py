from __future__ import annotations

import sys
from typing import Any

import pandas as pd

from technical_state_scanner.core.scanner import ScanResult, scan_symbol_with_frames
from technical_state_scanner.gui.charts import (
    EMA_COLUMNS,
    VEGAS_COLUMNS,
    build_summary_model,
    format_list,
    get_timeframe_key,
    get_timeframe_result,
    get_triggered_factor_labels,
    prepare_price_panel_data,
    prepare_volume_panel_data,
)
from technical_state_scanner.gui.widgets import (
    format_advanced_summary_text,
    format_details_text,
    format_summary_html,
    format_timeframe_summary_text,
    get_dark_stylesheet,
)
from technical_state_scanner.loader import normalize_symbol


class ScanWorker:
    """Small QObject worker wrapper created lazily after PySide6 is imported."""

    def __init__(self, ticker: str, count: int):
        from PySide6.QtCore import QObject, Signal

        class _Worker(QObject):
            finished = Signal(object, object)
            failed = Signal(str)

            def run(self) -> None:
                try:
                    result, frames = scan_symbol_with_frames(ticker, count=count)
                    self.finished.emit(result, frames)
                except Exception as exc:  # pragma: no cover - defensive GUI path
                    self.failed.emit(str(exc))

        self.object = _Worker()


def _set_plot_style(plot: Any, title: str) -> None:
    if hasattr(plot, "setBackground"):
        plot.setBackground("#0d1117")
    elif hasattr(plot, "getViewBox"):
        view_box = plot.getViewBox()
        if hasattr(view_box, "setBackgroundColor"):
            view_box.setBackgroundColor("#0d1117")
    plot.showGrid(x=True, y=True, alpha=0.22)
    plot.setTitle(title, color="#d8dee9", size="10pt")
    plot.getAxis("left").setTextPen("#8b949e")
    plot.getAxis("bottom").setTextPen("#8b949e")


class ChartStack:
    """Stacked pyqtgraph panels for selected timeframe data."""

    def __init__(self) -> None:
        import pyqtgraph as pg

        self.pg = pg
        self.layout = pg.GraphicsLayoutWidget()
        self.layout.setBackground("#0d1117")
        self.price_plot = self.layout.addPlot(row=0, col=0)
        self.volume_plot = self.layout.addPlot(row=1, col=0)
        self.signal_plot = self.layout.addPlot(row=2, col=0)
        _set_plot_style(self.price_plot, "Price / EMA / Vegas Tunnel")
        _set_plot_style(self.volume_plot, "Volume")
        _set_plot_style(self.signal_plot, "Signals")
        self.volume_plot.setMaximumHeight(150)
        self.signal_plot.setMaximumHeight(115)

    def clear(self) -> None:
        self.price_plot.clear()
        self.volume_plot.clear()
        self.signal_plot.clear()

    def render(
        self,
        frame: pd.DataFrame | None,
        timeframe_result: dict[str, Any],
    ) -> None:
        self.clear()
        price_data = prepare_price_panel_data(frame)
        volume_data = prepare_volume_panel_data(frame)
        if price_data.empty:
            self.signal_plot.addItem(self.pg.TextItem("No chart data available", color="#f2cc60"))
            return

        x_values = list(range(len(price_data)))
        self.price_plot.plot(
            x_values,
            price_data["Close"].to_numpy(dtype=float),
            pen=self.pg.mkPen("#f0f6fc", width=1.6),
            name="Close",
        )
        line_colors = {
            "EMA12": "#ffffff",
            "EMA144": "#f2cc60",
            "EMA169": "#d29922",
            "EMA576": "#3fb950",
            "EMA676": "#238636",
            "VegasLower": "#58a6ff",
            "VegasUpper": "#58a6ff",
        }
        for column in EMA_COLUMNS + VEGAS_COLUMNS:
            if column in price_data.columns:
                style = self.pg.QtCore.Qt.DashLine if column in VEGAS_COLUMNS else self.pg.QtCore.Qt.SolidLine
                self.price_plot.plot(
                    x_values,
                    price_data[column].to_numpy(dtype=float),
                    pen=self.pg.mkPen(line_colors.get(column, "#8b949e"), width=1.1, style=style),
                    name=column,
                )

        if not volume_data.empty:
            has_volume_surge = "F6" in timeframe_result.get("triggered_factors", [])
            brush = "#f2cc60" if has_volume_surge else "#30363d"
            bars = self.pg.BarGraphItem(
                x=list(range(len(volume_data))),
                height=volume_data["Volume"].to_numpy(dtype=float),
                width=0.72,
                brush=brush,
            )
            self.volume_plot.addItem(bars)

        labels = get_triggered_factor_labels(timeframe_result)
        label_text = "No factors triggered" if not labels else " | ".join(labels)
        color = "#8b949e" if not labels else "#58a6ff"
        item = self.pg.TextItem(label_text, color=color, anchor=(0, 0.5))
        self.signal_plot.addItem(item)
        item.setPos(0, 0.5)
        self.signal_plot.setYRange(0, 1)


class MainWindow:
    """Desktop scanner result viewer."""

    def __init__(self) -> None:
        from PySide6.QtCore import Qt
        from PySide6.QtWidgets import (
            QButtonGroup,
            QFrame,
            QHBoxLayout,
            QLabel,
            QLineEdit,
            QMainWindow,
            QPushButton,
            QRadioButton,
            QSpinBox,
            QSplitter,
            QTextEdit,
            QVBoxLayout,
            QWidget,
        )

        class _Window(QMainWindow):
            pass

        self.qt = Qt
        self.window = _Window()
        self.window.setWindowTitle("Technical State Scanner")
        self.window.resize(1360, 820)
        self.window.setStyleSheet(get_dark_stylesheet())

        self.result: ScanResult | None = None
        self.frames: dict[str, pd.DataFrame] = {}
        self.active_timeframe_label = "Daily"
        self.scan_thread = None
        self.scan_worker = None

        root = QWidget()
        root_layout = QVBoxLayout(root)
        root_layout.setContentsMargins(10, 10, 10, 10)
        root_layout.setSpacing(8)

        toolbar = QHBoxLayout()
        title = QLabel("Technical State Scanner")
        title.setObjectName("Title")
        toolbar.addWidget(title)

        self.ticker_input = QLineEdit("CRCL.US")
        self.ticker_input.setFixedWidth(140)
        toolbar.addWidget(self.ticker_input)

        self.timeframe_buttons = QButtonGroup(self.window)
        for label in ["4H", "Daily", "Weekly"]:
            button = QRadioButton(label)
            button.setChecked(label == self.active_timeframe_label)
            button.toggled.connect(lambda checked, value=label: self.on_timeframe_changed(value, checked))
            self.timeframe_buttons.addButton(button)
            toolbar.addWidget(button)

        self.count_input = QSpinBox()
        self.count_input.setRange(100, 2000)
        self.count_input.setSingleStep(50)
        self.count_input.setValue(700)
        toolbar.addWidget(QLabel("Candles"))
        toolbar.addWidget(self.count_input)

        self.scan_button = QPushButton("Scan")
        self.scan_button.clicked.connect(self.start_scan)
        toolbar.addWidget(self.scan_button)

        self.save_button = QPushButton("Save Report")
        self.save_button.setEnabled(False)
        toolbar.addWidget(self.save_button)

        source = QLabel("Data source: LongPort OpenAPI")
        source.setObjectName("Muted")
        toolbar.addStretch(1)
        toolbar.addWidget(source)
        root_layout.addLayout(toolbar)

        splitter = QSplitter(Qt.Horizontal)
        self.summary_panel = QFrame()
        self.summary_panel.setObjectName("SummaryPanel")
        summary_layout = QVBoxLayout(self.summary_panel)
        self.summary_label = QLabel("Enter a ticker and scan.")
        self.summary_label.setWordWrap(True)
        self.summary_label.setTextFormat(Qt.RichText)
        summary_layout.addWidget(self.summary_label)
        self.status_label = QLabel("Ready")
        self.status_label.setObjectName("Muted")
        summary_layout.addWidget(self.status_label)
        summary_layout.addStretch(1)

        chart_panel = QFrame()
        chart_panel.setObjectName("ChartPanel")
        chart_layout = QVBoxLayout(chart_panel)
        self.chart_stack = ChartStack()
        chart_layout.addWidget(self.chart_stack.layout, stretch=4)
        self.details_text = QTextEdit()
        self.details_text.setReadOnly(True)
        self.details_text.setMaximumHeight(180)
        chart_layout.addWidget(self.details_text, stretch=1)
        self.advanced_button = QPushButton("Show advanced factor diagnostics")
        self.advanced_button.setCheckable(True)
        self.advanced_button.toggled.connect(self.on_advanced_toggled)
        chart_layout.addWidget(self.advanced_button)
        self.advanced_text = QTextEdit()
        self.advanced_text.setReadOnly(True)
        self.advanced_text.setMaximumHeight(170)
        self.advanced_text.setVisible(False)
        chart_layout.addWidget(self.advanced_text)

        splitter.addWidget(self.summary_panel)
        splitter.addWidget(chart_panel)
        splitter.setSizes([330, 1000])
        root_layout.addWidget(splitter, stretch=1)

        self.window.setCentralWidget(root)

    def show(self) -> None:
        self.window.show()

    def start_scan(self) -> None:
        from PySide6.QtCore import QThread

        ticker = normalize_symbol(self.ticker_input.text())
        count = int(self.count_input.value())
        self.status_label.setText(f"Loading data and scanning {ticker}...")
        self.scan_button.setEnabled(False)

        self.scan_thread = QThread()
        self.scan_worker = ScanWorker(ticker, count).object
        self.scan_worker.moveToThread(self.scan_thread)
        self.scan_thread.started.connect(self.scan_worker.run)
        self.scan_worker.finished.connect(self.on_scan_finished)
        self.scan_worker.failed.connect(self.on_scan_failed)
        self.scan_worker.finished.connect(self.scan_thread.quit)
        self.scan_worker.failed.connect(self.scan_thread.quit)
        self.scan_thread.finished.connect(self.scan_thread.deleteLater)
        self.scan_thread.start()

    def on_scan_finished(self, result: ScanResult, frames: dict[str, pd.DataFrame]) -> None:
        self.result = result
        self.frames = frames
        self.scan_button.setEnabled(True)
        self.save_button.setEnabled(result.error is None)
        self.status_label.setText("Done" if result.error is None else f"Error: {result.error}")
        self.render_current_timeframe()

    def on_scan_failed(self, message: str) -> None:
        self.scan_button.setEnabled(True)
        self.status_label.setText(f"Error: {message}")

    def on_timeframe_changed(self, label: str, checked: bool) -> None:
        if not checked:
            return
        self.active_timeframe_label = label
        self.render_current_timeframe()

    def render_current_timeframe(self) -> None:
        timeframe_key = get_timeframe_key(self.active_timeframe_label)
        summary = build_summary_model(self.result, self.frames, timeframe_key)
        self.summary_label.setText(format_summary_html(summary))

        timeframe_result = get_timeframe_result(self.result, timeframe_key)
        frame = self.frames.get(timeframe_key)
        self.chart_stack.render(frame, timeframe_result)
        self.details_text.setPlainText(
            format_timeframe_summary_text(self.active_timeframe_label, timeframe_result)
        )
        self.advanced_text.setPlainText(
            format_advanced_summary_text(summary)
            + "\n\nAdvanced factor diagnostics\n"
            + format_details_text(timeframe_result)
        )
        if self.result and not self.result.error and not self.result.all_triggered_signals:
            self.status_label.setText("Done: no factors triggered.")
        elif self.result and self.result.all_triggered_signals:
            self.status_label.setText(f"Done: {format_list(self.result.all_triggered_signals)}")

    def on_advanced_toggled(self, checked: bool) -> None:
        self.advanced_text.setVisible(checked)
        self.advanced_button.setText(
            "Hide advanced factor diagnostics" if checked else "Show advanced factor diagnostics"
        )


def run_app() -> int:
    from PySide6.QtWidgets import QApplication

    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(run_app())
