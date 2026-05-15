from __future__ import annotations

from technical_state_scanner.core.scanner import load_universe_from_file


def test_load_universe_from_txt_file(tmp_path):
    """Create a TXT with tickers + comments + blanks, verify parsed correctly."""

    path = tmp_path / "watchlist.txt"
    path.write_text("AAPL.US\n\n# skip me\nMSFT.US\n", encoding="utf-8")

    assert load_universe_from_file(path) == ["AAPL.US", "MSFT.US"]


def test_load_universe_normalizes_symbols(tmp_path):
    """'aapl' becomes 'AAPL.US'."""

    path = tmp_path / "watchlist.txt"
    path.write_text("aapl\nmsft.us\n", encoding="utf-8")

    assert load_universe_from_file(path) == ["AAPL.US", "MSFT.US"]


def test_load_universe_deduplicates(tmp_path):
    """Repeated tickers appear once in result."""

    path = tmp_path / "watchlist.txt"
    path.write_text("AAPL\nAAPL.US\naapl\n", encoding="utf-8")

    assert load_universe_from_file(path) == ["AAPL.US"]
