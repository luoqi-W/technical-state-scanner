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

Scan symbols from a custom CSV, TXT, or JSON watchlist:

```bash
python main.py scan --universe-file data/universes/my_watchlist.csv
```

For CSV files, the first column is used by default. You can specify a column:

```bash
python main.py scan --universe-file data/universes/my_watchlist.csv --symbol-column ticker
```

TXT files should contain one ticker per line. Blank lines and lines beginning with `#` are ignored. JSON files may be a symbol array, such as `["AAPL", "MSFT"]`, or an object containing a `symbols` array.

Named local universe lists are supported when the files exist under `universes/` or `data/universes/`:

```bash
python main.py scan --universe sp500
```

```bash
python main.py scan --universe nasdaq
```

Recognized local files include:

- `universes/sp500.json`
- `universes/sp500.csv`
- `universes/sp500.txt`
- `universes/nasdaq.json`
- `universes/nasdaq.csv`
- `universes/nasdaq.txt`
- `data/universes/sp500.json`
- `data/universes/sp500.csv`
- `data/universes/sp500.txt`
- `data/universes/nasdaq.json`
- `data/universes/nasdaq.csv`
- `data/universes/nasdaq.txt`

Write universe CSV output to `reports/`:

```bash
python main.py scan --universe-file data/universes/my_watchlist.csv --output reports/universe_results.csv
```

If `--output` is omitted for a universe scan, a timestamped CSV is written under `reports/`.

## Pure Scan Mode

The CLI is a pure scan mode. It does not render charts.

You can make that explicit:

```bash
python main.py scan --ticker AAPL --no-charts
```

Charts are available in the React web UI.

## React Web UI

The production-style local website is served by FastAPI. On Windows, double-click:

```text
start_website.bat
```

Then open:

```text
http://127.0.0.1:8000
```

The batch file builds the React frontend when needed, starts the FastAPI backend, and opens the browser.

You can also start it manually:

```bash
python main.py server --host 127.0.0.1 --port 8000
```

The backend starts StockSelection-style automatic K-line updates in the background:

- pre-market, 4:00-9:30 AM ET: supplement `daily` + `weekly`
- intraday, 4:00 AM-8:00 PM ET: rolling update `15min` + `4hour` every 5 minutes
For frontend development, you can still run Vite in a second terminal:

```bash
cd frontend
npm install
npm run dev
```

## Historical K-Line Download

Backfill local K-line data from LongPort historical candlesticks into `data_store/scanner.duckdb` and `data_cache/`:

```bash
python main.py history --universe watchlist
```

By default this downloads `weekly`, `daily`, and `4hour` data. You can choose specific timeframes:

```bash
python main.py history --universe watchlist --timeframes daily weekly
```

Manual daily incremental updates are still available:

```bash
python main.py history --universe watchlist --loop
```

Manual 15-minute updates every 5 minutes are also available, but they are no longer required when the backend is running:

```bash
python main.py history --universe watchlist --timeframes 15min --loop --interval-minutes 5
```

For Windows Task Scheduler, create a daily task that runs this one-shot incremental command:

```bash
python main.py history --universe watchlist --max-pages 1
```

LongPort historical candlesticks return at most 1000 bars per request and are limited to 60 requests per 30 seconds, so the downloader throttles requests automatically.

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
