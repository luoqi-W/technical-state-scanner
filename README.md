# technical-state-scanner

LongPort multi-signal, multi-timeframe technical state scanner.

The scanner uses LongBridge / LongPort OpenAPI as the required market data source. It detects the six independent technical factors from `AGENTS.md`, reports every triggered signal, and calculates the configured multi-layer score. It does not use `yfinance`, does not create `primary_state` or `display_state`, and does not force sequential stage logic.

## Install

From the repository root:

```bash
python -m venv .venv
```

On macOS/Linux:

```bash
source .venv/bin/activate
pip install -e .
pip install -r requirements.txt
```

On Windows PowerShell:

```powershell
.\.venv\Scripts\Activate.ps1
pip install -e .
pip install -r requirements.txt
```

## Configure LongPort

Set these environment variables before running a scan:

- `LONGPORT_APP_KEY`
- `LONGPORT_APP_SECRET`
- `LONGPORT_ACCESS_TOKEN`

Compatible fallback names are also accepted:

- `LONGBRIDGE_APP_KEY`
- `LONGBRIDGE_APP_SECRET`
- `LONGBRIDGE_ACCESS_TOKEN`

If both sets are present, the `LONGPORT_*` names are preferred.

PowerShell example:

```powershell
$env:LONGPORT_APP_KEY="your_app_key"
$env:LONGPORT_APP_SECRET="your_app_secret"
$env:LONGPORT_ACCESS_TOKEN="your_access_token"
```

macOS/Linux example:

```bash
export LONGPORT_APP_KEY="your_app_key"
export LONGPORT_APP_SECRET="your_app_secret"
export LONGPORT_ACCESS_TOKEN="your_access_token"
```

Validate the environment:

```bash
python main.py validate-env
```

The package entrypoint also works after installation:

```bash
tech-state-validate-env
```

## Single-Stock Scan

Run a single-stock scan with either a LongPort-qualified symbol or a plain ticker. Plain U.S. tickers are normalized, so `AAPL` becomes `AAPL.US`.

```bash
python main.py scan --ticker AAPL.US
```

```bash
python main.py scan --ticker AAPL
```

Write a CSV report:

```bash
python main.py scan --ticker AAPL --output reports/results.csv
```

Write structured JSON-like output:

```bash
python main.py scan --ticker AAPL --json-output reports/result.json
```

## Universe Scan

Universe scans use lightweight results only: ticker, scores, triggered signals, triggered factors, factor confluence summary, timestamps, data source, and failure reason if any. Universe CSV output does not include chart data, chart images, or full factor diagnostic payloads.

Scan symbols from a custom CSV or TXT watchlist:

```bash
python main.py scan --universe-file data/universes/my_watchlist.csv
```

For CSV files, the first column is used by default. You can specify a column:

```bash
python main.py scan --universe-file data/universes/my_watchlist.csv --symbol-column ticker
```

TXT files should contain one ticker per line. Blank lines and lines beginning with `#` are ignored.

Named local universe lists are supported when the files exist under `universes/` or `data/universes/`:

```bash
python main.py scan --universe sp500
```

```bash
python main.py scan --universe nasdaq
```

Recognized local files include:

- `universes/sp500.csv`
- `universes/sp500.txt`
- `universes/nasdaq.csv`
- `universes/nasdaq.txt`
- `data/universes/sp500.csv`
- `data/universes/sp500.txt`
- `data/universes/nasdaq.csv`
- `data/universes/nasdaq.txt`

Write universe CSV output to `reports/`:

```bash
python main.py scan --universe-file data/universes/my_watchlist.csv --output reports/universe_results.csv
```

If `--output` is omitted for a universe scan, a timestamped CSV is written under `reports/`.

## Pure Scan Mode

The CLI is a pure scan mode. It does not require Streamlit and does not render charts.

You can make that explicit:

```bash
python main.py scan --ticker AAPL --no-charts
```

Charts are generated lazily only in the Streamlit UI result viewer: a chart is rendered only after the user selects a specific ticker and timeframe. Universe scans do not pre-render charts.

## Streamlit UI

Run the result viewer:

```bash
streamlit run src/technical_state_scanner/ui/app.py
```

The UI includes:

- a ticker search bar and Scan button for single-stock scans
- a persistent score summary that stays visible when switching timeframes
- a [4H] [Daily] [Weekly] selector
- a selected-timeframe candlestick chart with EMA12, EMA144, EMA169, EMA576, EMA676, and Vegas Tunnel lines when available
- selected-timeframe triggered factors, triggered signals, factor confluence, and diagnostics
- lightweight ranked universe result browsing

Universe browsing stays lightweight. It shows ticker, total score, triggered signals, triggered factors, factor confluence, timestamps, and failure reason when applicable. Charts are rendered lazily only after a ticker and timeframe are selected.

## Desktop GUI

The desktop viewer is a separate PySide6 / pyqtgraph app for a faster dark-theme dashboard experience. It keeps the Streamlit app available, but it does not use Streamlit as the main interactive surface.

Run it after installing dependencies:

```bash
python -m technical_state_scanner.gui.app
```

If the package is installed with `pip install -e .`, this command is also available:

```bash
tech-state-gui
```

The desktop GUI includes:

- compact top toolbar with ticker input, 4H / Daily / Weekly selector, candles count, Scan button, and LongPort data-source label
- left persistent score summary with ticker, latest date, latest close, total score, pre-multiplier score, coverage multiplier, all triggered signals, selected timeframe factors, confluence, and failure reason
- stacked chart area with price/EMA/Vegas lines, volume bars, and selected timeframe signal labels
- lazy rendering for only the selected ticker and selected timeframe

The desktop GUI consumes existing scanner/scoring outputs and LongPort OHLCV frames. It does not reimplement F1-F6, scoring, or data loading rules.

## Outputs

Single-stock structured JSON-like output preserves nested details:

- ticker
- total score
- scoring breakdown
- all triggered signals
- per-timeframe triggered factors and signals
- factor details
- factor confluence
- data source
- timestamps
- failure reason if applicable

Universe CSV output is lightweight and includes:

- ticker
- total score
- pre-multiplier score
- cross-timeframe all-factor coverage multiplier
- all triggered signals
- weekly / daily / four-hour triggered signals
- weekly / daily / four-hour triggered factors
- weekly / daily / four-hour confluence score
- factor confluence summary
- data source
- timestamps
- failure reason if applicable

## Tests

```bash
python -m pytest -q
```
