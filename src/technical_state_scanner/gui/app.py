from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

import pandas as pd

from technical_state_scanner.core.csv_output import write_scan_results_to_csv
from technical_state_scanner.core.scanner import (
    ScanResult,
    load_symbols_from_file,
    scan_symbol_with_frames,
    scan_universe_concurrent,
)
from technical_state_scanner.gui.charts import (
    CHART_WINDOWS_DAYS,
    build_summary_model,
    candle_width_for_timeframe,
    format_list,
    get_timeframe_key,
    get_timeframe_result,
    get_triggered_factor_labels,
    prepare_ema_overlay_data,
    prepare_finplot_ohlc_data,
    x_bounds_for_timeframe,
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
    """Small QObject worker wrapper created lazily after PyQt6 is imported."""

    def __init__(self, mode: str, target: str, count: int, workers: int = 3):
        from PyQt6.QtCore import QObject, pyqtSignal

        class _Worker(QObject):
            finished = pyqtSignal(object, object)
            failed = pyqtSignal(str)
            progress = pyqtSignal(str)

            def run(self) -> None:
                try:
                    if mode == "universe":
                        symbols = load_symbols_from_file(target)

                        def _progress(done: int, total: int, symbol: str) -> None:
                            self.progress.emit(f"Scanned {done}/{total}: {symbol}")

                        results = scan_universe_concurrent(
                            symbols,
                            count=count,
                            max_workers=workers,
                            on_progress=_progress,
                        )
                        self.finished.emit(results, {})
                        return

                    result, frames = scan_symbol_with_frames(target, count=count)
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


class FinplotChart:
    """Embedded finplot candlestick chart for selected timeframe data."""

    def __init__(self, parent: Any) -> None:
        import finplot as fplt
        import pyqtgraph as pg

        self.fplt = fplt
        self.plot_item = fplt.create_plot_widget(parent, init_zoom_periods=30)
        self.widget = pg.PlotWidget(plotItem=self.plot_item)
        self.widget.setBackground("#050914")
        _set_plot_style(self.plot_item, "K Line / EMA / Vegas Tunnel")

    def clear(self) -> None:
        self.plot_item.clear()

    def render(
        self,
        frame: pd.DataFrame | None,
        timeframe_result: dict[str, Any],
        days: int,
        timeframe_key: str,
    ) -> None:
        self.clear()
        chart_data = prepare_finplot_ohlc_data(frame, days, timeframe_key=timeframe_key)
        if chart_data.empty:
            self.fplt.add_text((0, 0), "No chart data available", color="#f2cc60", ax=self.plot_item)
            self.fplt.refresh()
            return

        line_colors = {
            "EMA12": "#ffffff",
            "EMA144": "#f2cc60",
            "EMA169": "#d29922",
            "EMA576": "#3fb950",
            "EMA676": "#238636",
        }
        self.fplt.candlestick_ochl(
            chart_data[["Open", "Close", "High", "Low"]],
            ax=self.plot_item,
            candle_width=candle_width_for_timeframe(timeframe_key),
        )
        for column, series in prepare_ema_overlay_data(chart_data).items():
            self.fplt.plot(
                series.index,
                series.to_numpy(dtype=float),
                ax=self.plot_item,
                color=line_colors.get(column, "#8b949e"),
                width=1.4 if column == "EMA12" else 1.1,
            )

        labels = get_triggered_factor_labels(timeframe_result)
        if labels:
            y_pos = float(chart_data["High"].max())
            self.fplt.add_text(
                (chart_data.index[-1], y_pos),
                " | ".join(labels),
                color="#58a6ff",
                anchor=(1, 1),
                ax=self.plot_item,
            )
        x_min, x_max = x_bounds_for_timeframe(timeframe_key, chart_data)
        self.fplt.set_x_pos(x_min, x_max, ax=self.plot_item)
        self._set_price_range(chart_data)
        self.fplt.refresh()

    def _set_price_range(self, chart_data: pd.DataFrame) -> None:
        if not {"High", "Low"}.issubset(chart_data.columns):
            return
        high = pd.to_numeric(chart_data["High"], errors="coerce").max()
        low = pd.to_numeric(chart_data["Low"], errors="coerce").min()
        if pd.isna(high) or pd.isna(low) or high <= low:
            return
        padding = (high - low) * 0.06
        if hasattr(self.plot_item, "setYRange"):
            self.plot_item.setYRange(float(low - padding), float(high + padding), padding=0)


class MainWindow:
    """Desktop scanner result viewer."""

    def __init__(self) -> None:
        from PyQt6.QtCore import Qt
        from PyQt6.QtWidgets import (
            QButtonGroup,
            QFileDialog,
            QComboBox,
            QFrame,
            QGridLayout,
            QHBoxLayout,
            QHeaderView,
            QLabel,
            QLineEdit,
            QMainWindow,
            QPushButton,
            QRadioButton,
            QSpinBox,
            QSplitter,
            QTableWidget,
            QTextEdit,
            QVBoxLayout,
            QWidget,
        )

        class _Window(QMainWindow):
            pass

        self.qt = Qt
        self.window = _Window()
        self.window.setWindowTitle("Technical State Scanner")
        self.window.resize(1480, 900)
        self.window.setStyleSheet(get_dark_stylesheet())

        self.result: ScanResult | None = None
        self.universe_results: list[ScanResult] = []
        self.frames: dict[str, pd.DataFrame] = {}
        self.active_timeframe_label = "Daily"
        self.factor_cards: dict[str, Any] = {}
        self.scan_thread = None
        self.scan_worker = None
        self.file_dialog = QFileDialog

        root = QWidget()
        root_layout = QVBoxLayout(root)
        root_layout.setContentsMargins(14, 14, 14, 14)
        root_layout.setSpacing(10)

        scan_bar = QFrame()
        scan_bar.setObjectName("ScanBar")
        toolbar = QGridLayout(scan_bar)
        toolbar.setContentsMargins(12, 10, 12, 10)
        toolbar.setHorizontalSpacing(10)
        toolbar.setVerticalSpacing(8)
        title = QLabel("Technical State Scanner")
        title.setObjectName("Title")
        toolbar.addWidget(title, 0, 0)

        self.scan_mode_group = QButtonGroup(self.window)
        self.single_mode_button = QRadioButton("Single ticker")
        self.file_mode_button = QRadioButton("Local file")
        self.single_mode_button.setChecked(True)
        for button in [self.single_mode_button, self.file_mode_button]:
            self.scan_mode_group.addButton(button)
        self.single_mode_button.toggled.connect(self.on_scan_mode_changed)
        toolbar.addWidget(self.single_mode_button, 0, 1)
        toolbar.addWidget(self.file_mode_button, 0, 2)

        self.ticker_input = QLineEdit("CRCL.US")
        self.ticker_input.setPlaceholderText("Ticker, e.g. AAPL.US")
        self.ticker_input.setMinimumWidth(150)
        self.ticker_label = QLabel("Ticker")
        toolbar.addWidget(self.ticker_label, 0, 3)
        toolbar.addWidget(self.ticker_input, 0, 4)

        self.file_input = QLineEdit(str(Path("universes") / "watchlist.txt"))
        self.file_input.setPlaceholderText("Choose .txt, .list, or .csv")
        self.file_input.setVisible(False)
        self.file_button = QPushButton("Browse")
        self.file_button.setVisible(False)
        self.file_button.clicked.connect(self.choose_universe_file)
        toolbar.addWidget(QLabel("File"), 0, 5)
        self.file_label = toolbar.itemAtPosition(0, 5).widget()
        self.file_label.setVisible(False)
        toolbar.addWidget(self.file_input, 0, 6)
        toolbar.addWidget(self.file_button, 0, 7)

        self.count_input = QSpinBox()
        self.count_input.setRange(100, 2000)
        self.count_input.setSingleStep(50)
        self.count_input.setValue(700)
        toolbar.addWidget(QLabel("Candles"), 1, 1)
        toolbar.addWidget(self.count_input, 1, 2)

        self.workers_input = QSpinBox()
        self.workers_input.setRange(1, 8)
        self.workers_input.setValue(3)
        self.workers_input.setVisible(False)
        self.workers_label = QLabel("Workers")
        self.workers_label.setVisible(False)
        toolbar.addWidget(self.workers_label, 1, 3)
        toolbar.addWidget(self.workers_input, 1, 4)

        self.chart_window_input = QComboBox()
        self.chart_window_input.addItems([f"{days} days" for days in CHART_WINDOWS_DAYS])
        self.chart_window_input.setCurrentText("30 days")
        self.chart_window_input.currentTextChanged.connect(lambda _value: self.render_current_timeframe())
        toolbar.addWidget(QLabel("Chart Window"), 1, 8)
        toolbar.addWidget(self.chart_window_input, 1, 9)

        self.scan_button = QPushButton("Scan")
        self.scan_button.setObjectName("PrimaryButton")
        self.scan_button.clicked.connect(self.start_scan)
        toolbar.addWidget(self.scan_button, 0, 8)

        self.save_button = QPushButton("Save Report")
        self.save_button.setEnabled(False)
        self.save_button.clicked.connect(self.save_report)
        toolbar.addWidget(self.save_button, 0, 9)

        source = QLabel("Data source: LongPort OpenAPI")
        source.setObjectName("Muted")
        toolbar.addWidget(source, 1, 10)
        toolbar.setColumnStretch(6, 1)
        root_layout.addWidget(scan_bar)

        splitter = QSplitter(Qt.Orientation.Horizontal)
        self.summary_panel = QFrame()
        self.summary_panel.setObjectName("SummaryPanel")
        summary_layout = QVBoxLayout(self.summary_panel)
        self.summary_label = QLabel("Enter a ticker and scan.")
        self.summary_label.setWordWrap(True)
        self.summary_label.setTextFormat(Qt.TextFormat.RichText)
        summary_layout.addWidget(self.summary_label)
        self.status_label = QLabel("Ready")
        self.status_label.setObjectName("Muted")
        summary_layout.addWidget(self.status_label)
        self.details_text = QTextEdit()
        self.details_text.setReadOnly(True)
        self.details_text.setObjectName("SideDetails")
        self.details_text.setMinimumHeight(170)
        self.details_text.setMaximumHeight(260)
        summary_layout.addWidget(self.details_text)
        summary_layout.addStretch(1)

        chart_panel = QFrame()
        chart_panel.setObjectName("ChartPanel")
        chart_layout = QVBoxLayout(chart_panel)
        timeframe_panel = QFrame()
        timeframe_panel.setObjectName("TimeframePanel")
        timeframe_layout = QHBoxLayout(timeframe_panel)
        timeframe_layout.setContentsMargins(8, 8, 8, 8)
        timeframe_layout.setSpacing(8)
        self.timeframe_card_buttons = QButtonGroup(self.window)
        self.timeframe_card_buttons.setExclusive(True)
        for label in ["4H", "Daily", "Weekly"]:
            button = QPushButton(f"{label}\nNo scan result")
            button.setObjectName("TimeframeCardButton")
            button.setCheckable(True)
            button.setChecked(label == self.active_timeframe_label)
            button.setMinimumHeight(92)
            button.clicked.connect(lambda _checked, value=label: self.on_timeframe_card_clicked(value))
            self.timeframe_card_buttons.addButton(button)
            timeframe_layout.addWidget(button)
            self.factor_cards[label] = button
        chart_layout.addWidget(timeframe_panel)

        self.chart_stack = FinplotChart(self.window)
        self.window.axs = [self.chart_stack.plot_item]
        chart_layout.addWidget(self.chart_stack.widget, stretch=5)

        self.universe_table = QTableWidget()
        self.universe_table.setColumnCount(7)
        self.universe_table.setHorizontalHeaderLabels(
            ["Ticker", "Score", "Signals", "Daily", "Weekly", "4H", "Failed Reason"]
        )
        self.universe_table.setVisible(False)
        self.universe_table.setAlternatingRowColors(True)
        self.universe_table.verticalHeader().setVisible(False)
        self.universe_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.universe_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.universe_table.cellDoubleClicked.connect(self.open_universe_row_as_single)
        header = self.universe_table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(3, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(4, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(5, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(6, QHeaderView.ResizeMode.Stretch)
        chart_layout.addWidget(self.universe_table, stretch=2)

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
        splitter.setSizes([380, 1000])
        root_layout.addWidget(splitter, stretch=1)

        self.window.setCentralWidget(root)

    def is_universe_mode(self) -> bool:
        return self.file_mode_button.isChecked()

    def on_scan_mode_changed(self) -> None:
        universe_mode = self.is_universe_mode()
        self.ticker_label.setVisible(not universe_mode)
        self.ticker_input.setVisible(not universe_mode)
        self.file_label.setVisible(universe_mode)
        self.file_input.setVisible(universe_mode)
        self.file_button.setVisible(universe_mode)
        self.workers_label.setVisible(universe_mode)
        self.workers_input.setVisible(universe_mode)
        self.universe_table.setVisible(universe_mode and bool(self.universe_results))
        self.chart_stack.widget.setVisible(not universe_mode)
        self.details_text.setVisible(not universe_mode)
        self.advanced_button.setVisible(not universe_mode)
        self.advanced_text.setVisible(not universe_mode and self.advanced_button.isChecked())
        self.status_label.setText("Ready for local file scan." if universe_mode else "Ready for single ticker scan.")

    def choose_universe_file(self) -> None:
        path, _filter = self.file_dialog.getOpenFileName(
            self.window,
            "Choose local ticker file",
            str(Path.cwd() / "universes"),
            "Ticker files (*.txt *.list *.csv);;All files (*.*)",
        )
        if path:
            self.file_input.setText(path)

    def show(self) -> None:
        self.window.show()

    def start_scan(self) -> None:
        from PyQt6.QtCore import QThread

        mode = "universe" if self.is_universe_mode() else "single"
        target = self.file_input.text().strip() if mode == "universe" else normalize_symbol(self.ticker_input.text())
        count = int(self.count_input.value())
        workers = int(self.workers_input.value())
        self.status_label.setText(
            f"Loading local file and scanning {target}..." if mode == "universe"
            else f"Loading data and scanning {target}..."
        )
        self.scan_button.setEnabled(False)
        self.save_button.setEnabled(False)
        self.universe_table.setVisible(mode == "universe")
        self.chart_stack.widget.setVisible(mode != "universe")
        self.details_text.setVisible(mode != "universe")
        self.advanced_button.setVisible(mode != "universe")
        self.advanced_text.setVisible(mode != "universe" and self.advanced_button.isChecked())

        self.scan_thread = QThread()
        self.scan_worker = ScanWorker(mode, target, count, workers=workers).object
        self.scan_worker.moveToThread(self.scan_thread)
        self.scan_thread.started.connect(self.scan_worker.run)
        self.scan_worker.finished.connect(self.on_scan_finished)
        self.scan_worker.failed.connect(self.on_scan_failed)
        self.scan_worker.progress.connect(self.status_label.setText)
        self.scan_worker.finished.connect(self.scan_thread.quit)
        self.scan_worker.failed.connect(self.scan_thread.quit)
        self.scan_thread.finished.connect(self.scan_thread.deleteLater)
        self.scan_thread.start()

    def on_scan_finished(self, result: ScanResult | list[ScanResult], frames: dict[str, pd.DataFrame]) -> None:
        if isinstance(result, list):
            self.universe_results = result
            self.result = result[0] if result else None
            self.frames = {}
            self.scan_button.setEnabled(True)
            self.save_button.setEnabled(bool(result))
            self.status_label.setText(f"Done: scanned {len(result)} symbols. Double-click a row to inspect charts.")
            self.render_universe_table()
            self.summary_label.setText(
                f"<div style='line-height:1.6;'><h2 style='color:#fff;'>Local File Scan</h2>"
                f"<p style='color:#8b949e;'>Finished {len(result)} symbols.</p>"
                f"<p style='color:#58a6ff;font-size:26px;font-weight:700;'>"
                f"Top Score: {(result[0].total_score if result else 0.0):.1f}</p></div>"
            )
            return

        self.result = result
        self.universe_results = []
        self.frames = frames
        self.scan_button.setEnabled(True)
        self.save_button.setEnabled(result.error is None)
        self.status_label.setText("Done" if result.error is None else f"Error: {result.error}")
        self.render_current_timeframe()

    def on_scan_failed(self, message: str) -> None:
        self.scan_button.setEnabled(True)
        self.status_label.setText(f"Error: {message}")

    def render_universe_table(self) -> None:
        from PyQt6.QtWidgets import QTableWidgetItem

        self.universe_table.setRowCount(len(self.universe_results))
        for row, result in enumerate(self.universe_results):
            weekly = result.timeframe_results.get("weekly", {})
            daily = result.timeframe_results.get("daily", {})
            hour4 = result.timeframe_results.get("4hour", {})
            values = [
                result.ticker,
                f"{result.total_score:.1f}",
                format_list(result.all_triggered_signals),
                format_list(daily.get("triggered_factors", [])),
                format_list(weekly.get("triggered_factors", [])),
                format_list(hour4.get("triggered_factors", [])),
                result.error or "None",
            ]
            for column, value in enumerate(values):
                item = QTableWidgetItem(value)
                if column == 1:
                    item.setTextAlignment(self.qt.AlignmentFlag.AlignRight | self.qt.AlignmentFlag.AlignVCenter)
                self.universe_table.setItem(row, column, item)

    def open_universe_row_as_single(self, row: int, _column: int) -> None:
        if row < 0 or row >= len(self.universe_results):
            return
        self.ticker_input.setText(self.universe_results[row].ticker)
        self.single_mode_button.setChecked(True)
        self.start_scan()

    def save_report(self) -> None:
        if self.universe_results:
            path = write_scan_results_to_csv(self.universe_results)
        elif self.result is not None:
            path = write_scan_results_to_csv([self.result])
        else:
            return
        self.status_label.setText(f"Report saved: {path}")

    def on_timeframe_card_clicked(self, label: str) -> None:
        self.active_timeframe_label = label
        self.render_current_timeframe()

    def chart_window_days(self) -> int:
        text = self.chart_window_input.currentText()
        try:
            return int(text.split()[0])
        except (TypeError, ValueError, IndexError):
            return 10

    def render_timeframe_factor_cards(self) -> None:
        for label, button in self.factor_cards.items():
            timeframe_key = get_timeframe_key(label)
            timeframe_result = get_timeframe_result(self.result, timeframe_key)
            signals = timeframe_result.get("triggered_signals", [])
            signal_text = format_list(signals) if signals else "No triggered signals"
            button.setText(f"{label}\n{signal_text}")
            button.setChecked(label == self.active_timeframe_label)

    def render_current_timeframe(self) -> None:
        timeframe_key = get_timeframe_key(self.active_timeframe_label)
        summary = build_summary_model(self.result, self.frames, timeframe_key)
        self.summary_label.setText(format_summary_html(summary))
        self.render_timeframe_factor_cards()

        timeframe_result = get_timeframe_result(self.result, timeframe_key)
        frame = self.frames.get(timeframe_key)
        self.chart_stack.render(frame, timeframe_result, self.chart_window_days(), timeframe_key)
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
    from PyQt6.QtWidgets import QApplication

    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    try:
        import finplot as fplt

        fplt.show(qt_exec=False)
    except ImportError:
        pass
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(run_app())
