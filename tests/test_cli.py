"""Tests for main.py scan command wiring."""

from __future__ import annotations

from pathlib import Path

import main
from technical_state_scanner.core.scanner import LightweightUniverseResult, ScanResult


def _sample_scan_result(ticker: str = "AAPL.US") -> ScanResult:
    return ScanResult(
        ticker=ticker,
        total_score=12.0,
        pre_multiplier_score=12.0,
        cross_timeframe_all_factor_coverage_multiplier=1.0,
        all_triggered_signals=["Vegas Alignment"],
        base_timeframe_scores={"F1": {"score": 12.0}},
        factor_confluence_scores={"weekly": {}, "daily": {}, "4hour": {}},
        timeframe_results={
            "weekly": {"triggered_signals": [], "triggered_factors": [], "details": {}},
            "daily": {
                "triggered_signals": ["Vegas Alignment"],
                "triggered_factors": ["F1"],
                "details": {"F1": {"timestamp": "2026-01-01T00:00:00+00:00"}},
            },
            "4hour": {"triggered_signals": [], "triggered_factors": [], "details": {}},
        },
        notes=[],
    )


def _sample_lightweight_result(ticker: str = "AAPL.US") -> LightweightUniverseResult:
    return LightweightUniverseResult(
        ticker=ticker,
        scores={
            "total_score": 12.0,
            "pre_multiplier_score": 12.0,
            "cross_timeframe_all_factor_coverage_multiplier": 1.0,
            "base_timeframe_scores": {"F1": {"score": 12.0}},
        },
        triggered_signals=["Vegas Alignment"],
        triggered_factors=["F1"],
        timeframe_triggered_signals={"weekly": [], "daily": ["Vegas Alignment"], "4hour": []},
        timeframe_triggered_factors={"weekly": [], "daily": ["F1"], "4hour": []},
        factor_confluence={"weekly": {}, "daily": {"score": 0}, "4hour": {}},
        timestamps={"weekly": {}, "daily": {"F1": "2026-01-01T00:00:00+00:00"}, "4hour": {}},
    )


def test_scan_argument_parser_supports_single_ticker_command():
    args = main.build_parser().parse_args(["scan", "--ticker", "AAPL", "--no-charts"])

    assert args.command == "scan"
    assert args.ticker == "AAPL"
    assert args.no_charts is True


def test_single_stock_command_calls_scanner_and_outputs(monkeypatch, tmp_path):
    calls = {}

    def fake_scan_symbol(ticker, count):
        calls["scan_symbol"] = (ticker, count)
        return _sample_scan_result("AAPL.US")

    def fake_write_json(result, output_path=None, base_path="."):
        calls["json"] = (result.ticker, output_path)
        Path(output_path).parent.mkdir(parents=True, exist_ok=True)
        Path(output_path).write_text("{}", encoding="utf-8")
        return output_path

    def fake_write_csv(results, output_path=None, base_path="."):
        calls["csv"] = ([result.ticker for result in results], output_path)
        Path(output_path).parent.mkdir(parents=True, exist_ok=True)
        Path(output_path).write_text("ticker\nAAPL.US\n", encoding="utf-8")
        return output_path

    monkeypatch.setattr(main, "scan_symbol", fake_scan_symbol)
    monkeypatch.setattr(main, "write_single_scan_result_to_json", fake_write_json)
    monkeypatch.setattr(main, "write_scan_results_to_csv", fake_write_csv)

    code = main.main([
        "scan",
        "--ticker",
        "AAPL",
        "--output",
        str(tmp_path / "reports" / "single.csv"),
        "--json-output",
        str(tmp_path / "reports" / "single.json"),
        "--no-charts",
    ])

    assert code == 0
    assert calls["scan_symbol"] == ("AAPL", 700)
    assert calls["csv"][0] == ["AAPL.US"]
    assert calls["json"][0] == "AAPL.US"


def test_universe_file_command_loads_symbols_and_writes_lightweight_csv(monkeypatch, tmp_path):
    calls = {}

    def fake_load_symbols_from_file(path, symbol_column=None):
        calls["load_symbols"] = (path, symbol_column)
        return ["AAPL.US", "TSLA.US"]

    def fake_scan_universe_lightweight(symbols, count):
        calls["scan_universe"] = (symbols, count)
        return [_sample_lightweight_result("AAPL.US")]

    def fake_write_universe_results_to_csv(results, output_path=None, base_path="."):
        calls["csv"] = ([result.ticker for result in results], output_path)
        Path(output_path).parent.mkdir(parents=True, exist_ok=True)
        Path(output_path).write_text("ticker\nAAPL.US\n", encoding="utf-8")
        return output_path

    monkeypatch.setattr(main, "load_symbols_from_file", fake_load_symbols_from_file)
    monkeypatch.setattr(main, "scan_universe_lightweight", fake_scan_universe_lightweight)
    monkeypatch.setattr(main, "write_universe_results_to_csv", fake_write_universe_results_to_csv)

    code = main.main([
        "scan",
        "--universe-file",
        "data/universes/my_watchlist.csv",
        "--symbol-column",
        "ticker",
        "--output",
        str(tmp_path / "reports" / "universe.csv"),
    ])

    assert code == 0
    assert calls["load_symbols"] == ("data/universes/my_watchlist.csv", "ticker")
    assert calls["scan_universe"] == (["AAPL.US", "TSLA.US"], 700)
    assert calls["csv"][0] == ["AAPL.US"]


def test_named_universe_command_uses_local_named_universe_loader(monkeypatch):
    calls = {}

    def fake_load_named_universe(name):
        calls["universe"] = name
        return ["AAPL.US"]

    monkeypatch.setattr(main, "load_named_universe", fake_load_named_universe)
    monkeypatch.setattr(main, "scan_universe_lightweight", lambda symbols, count: [_sample_lightweight_result("AAPL.US")])
    monkeypatch.setattr(main, "write_universe_results_to_csv", lambda results, output_path=None, base_path=".": "reports/out.csv")

    code = main.main(["scan", "--universe", "sp500"])

    assert code == 0
    assert calls["universe"] == "sp500"


def test_no_charts_pure_scan_path_does_not_call_chart_rendering(monkeypatch):
    called = {"chart": False}

    def fake_chart_renderer(*args, **kwargs):
        called["chart"] = True

    monkeypatch.setattr(main, "scan_symbol", lambda ticker, count: _sample_scan_result("AAPL.US"))
    monkeypatch.setattr(main, "render_chart", fake_chart_renderer, raising=False)

    code = main.main(["scan", "--ticker", "AAPL", "--no-charts"])

    assert code == 0
    assert called["chart"] is False


def test_readme_examples_match_supported_commands():
    readme = Path("README.md").read_text(encoding="utf-8")
    parser = main.build_parser()
    examples = [
        ["scan", "--ticker", "AAPL.US"],
        ["scan", "--ticker", "AAPL"],
        ["scan", "--universe-file", "data/universes/my_watchlist.csv"],
        ["scan", "--universe", "sp500"],
        ["scan", "--universe", "nasdaq"],
        ["scan", "--ticker", "AAPL", "--output", "reports/results.csv"],
        ["scan", "--ticker", "AAPL", "--json-output", "reports/result.json"],
        ["scan", "--ticker", "AAPL", "--no-charts"],
    ]

    for example in examples:
        command_text = "python main.py " + " ".join(example)
        assert command_text in readme
        assert parser.parse_args(example).command == "scan"
