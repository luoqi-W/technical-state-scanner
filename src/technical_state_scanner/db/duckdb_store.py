"""DuckDB + Parquet unified storage for candlestick data.

Provides a ``candlesticks`` table backed by DuckDB with automatic
de-duplication on (symbol, timeframe, timestamp).  Parquet export is
available for portability and compatibility with the legacy cache layer.
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import duckdb
import pandas as pd

DB_PATH = Path("data_store") / "scanner.duckdb"
PARQUET_EXPORT_ROOT = Path("data_store") / "parquet"

OHLCV_COLUMNS = ["Open", "High", "Low", "Close", "Volume"]

_CREATE_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS candlesticks (
    symbol       VARCHAR NOT NULL,
    timeframe    VARCHAR NOT NULL,
    timestamp    TIMESTAMPTZ NOT NULL,
    open         DOUBLE NOT NULL,
    high         DOUBLE NOT NULL,
    low          DOUBLE NOT NULL,
    close        DOUBLE NOT NULL,
    volume       DOUBLE NOT NULL,
    PRIMARY KEY (symbol, timeframe, timestamp)
);
"""


def _ensure_db_dir() -> None:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)


def get_connection(db_path: Path | None = None) -> duckdb.DuckDBPyConnection:
    path = db_path or DB_PATH
    _ensure_db_dir()
    conn = duckdb.connect(str(path))
    conn.execute(_CREATE_TABLE_SQL)
    return conn


def upsert_candles(
    df: pd.DataFrame,
    symbol: str,
    timeframe: str,
    conn: duckdb.DuckDBPyConnection | None = None,
) -> int:
    """Insert or update candlestick rows.  Duplicates on (symbol, timeframe, timestamp) are
    replaced with the new values (automatic de-duplication).

    Returns the number of rows written.
    """
    if df.empty:
        return 0

    own_conn = conn is None
    if own_conn:
        conn = get_connection()

    frame = df.copy()
    if not isinstance(frame.index, pd.DatetimeIndex):
        raise ValueError("DataFrame index must be a DatetimeIndex.")

    frame = frame.reset_index()
    ts_col = frame.columns[0]
    frame = frame.rename(columns={ts_col: "timestamp"})
    frame["timestamp"] = pd.to_datetime(frame["timestamp"], utc=True)
    frame["symbol"] = symbol.upper()
    frame["timeframe"] = timeframe

    rename_map = {"Open": "open", "High": "high", "Low": "low", "Close": "close", "Volume": "volume"}
    frame = frame.rename(columns=rename_map)

    columns = ["symbol", "timeframe", "timestamp", "open", "high", "low", "close", "volume"]
    insert_df = frame[columns]

    conn.execute(
        """
        INSERT OR REPLACE INTO candlesticks
        SELECT * FROM insert_df
        """,
    )
    count = len(insert_df)

    if own_conn:
        conn.close()
    return count


def read_candles(
    symbol: str,
    timeframe: str,
    limit: int | None = None,
    since: datetime | None = None,
    conn: duckdb.DuckDBPyConnection | None = None,
) -> pd.DataFrame:
    """Read candlestick data from DuckDB, returned as a pandas OHLCV DataFrame
    with a UTC DatetimeIndex.
    """
    own_conn = conn is None
    if own_conn:
        conn = get_connection()

    query = "SELECT timestamp, open, high, low, close, volume FROM candlesticks WHERE symbol = ? AND timeframe = ?"
    params: list[Any] = [symbol.upper(), timeframe]

    if since is not None:
        query += " AND timestamp >= ?"
        params.append(since)

    if limit is not None:
        query = f"SELECT * FROM ({query} ORDER BY timestamp DESC LIMIT ?) ORDER BY timestamp ASC"
        params.append(limit)
    else:
        query += " ORDER BY timestamp ASC"

    result = conn.execute(query, params).fetchdf()

    if own_conn:
        conn.close()

    if result.empty:
        return pd.DataFrame(columns=OHLCV_COLUMNS)

    result = result.rename(columns={
        "open": "Open", "high": "High", "low": "Low", "close": "Close", "volume": "Volume",
    })
    result["timestamp"] = pd.to_datetime(result["timestamp"], utc=True)
    result = result.set_index("timestamp").sort_index()
    result.index = pd.DatetimeIndex(result.index, tz="UTC")
    return result[OHLCV_COLUMNS]


def get_latest_timestamp(
    symbol: str,
    timeframe: str,
    conn: duckdb.DuckDBPyConnection | None = None,
) -> datetime | None:
    """Return the most recent bar timestamp, or None if no data exists."""
    own_conn = conn is None
    if own_conn:
        conn = get_connection()

    row = conn.execute(
        "SELECT MAX(timestamp) FROM candlesticks WHERE symbol = ? AND timeframe = ?",
        [symbol.upper(), timeframe],
    ).fetchone()

    if own_conn:
        conn.close()

    if row is None or row[0] is None:
        return None
    ts = row[0]
    if hasattr(ts, "tzinfo") and ts.tzinfo is None:
        ts = ts.replace(tzinfo=timezone.utc)
    return ts


def get_bar_count(
    symbol: str,
    timeframe: str,
    conn: duckdb.DuckDBPyConnection | None = None,
) -> int:
    """Return the number of stored bars for a symbol+timeframe pair."""
    own_conn = conn is None
    if own_conn:
        conn = get_connection()

    row = conn.execute(
        "SELECT COUNT(*) FROM candlesticks WHERE symbol = ? AND timeframe = ?",
        [symbol.upper(), timeframe],
    ).fetchone()

    if own_conn:
        conn.close()

    return int(row[0]) if row else 0


def export_to_parquet(
    symbol: str,
    timeframe: str,
    output_dir: Path | None = None,
    conn: duckdb.DuckDBPyConnection | None = None,
) -> Path:
    """Export a symbol+timeframe slice to a standalone Parquet file."""
    export_root = output_dir or PARQUET_EXPORT_ROOT
    out_path = export_root / timeframe / f"{symbol.upper()}.parquet"
    out_path.parent.mkdir(parents=True, exist_ok=True)

    df = read_candles(symbol, timeframe, conn=conn)
    if df.empty:
        raise RuntimeError(f"No data to export for {symbol}/{timeframe}.")
    df.to_parquet(out_path)
    return out_path


def import_from_parquet(
    parquet_path: Path,
    symbol: str,
    timeframe: str,
    conn: duckdb.DuckDBPyConnection | None = None,
) -> int:
    """Import a Parquet file into the DuckDB candlesticks table."""
    df = pd.read_parquet(parquet_path)
    if not isinstance(df.index, pd.DatetimeIndex):
        if "timestamp" in df.columns:
            df = df.set_index("timestamp")
        elif "Datetime" in df.columns:
            df = df.set_index("Datetime")
    df.index = pd.to_datetime(df.index, utc=True)
    df.index = pd.DatetimeIndex(df.index, tz="UTC")
    return upsert_candles(df, symbol, timeframe, conn=conn)


def delete_candles(
    symbol: str | None = None,
    timeframe: str | None = None,
    conn: duckdb.DuckDBPyConnection | None = None,
) -> int:
    """Delete candlestick rows.  Pass None for both to truncate the table."""
    own_conn = conn is None
    if own_conn:
        conn = get_connection()

    if symbol is None and timeframe is None:
        count = conn.execute("SELECT COUNT(*) FROM candlesticks").fetchone()[0]
        conn.execute("DELETE FROM candlesticks")
    elif symbol is not None and timeframe is not None:
        count = conn.execute(
            "SELECT COUNT(*) FROM candlesticks WHERE symbol = ? AND timeframe = ?",
            [symbol.upper(), timeframe],
        ).fetchone()[0]
        conn.execute(
            "DELETE FROM candlesticks WHERE symbol = ? AND timeframe = ?",
            [symbol.upper(), timeframe],
        )
    elif symbol is not None:
        count = conn.execute(
            "SELECT COUNT(*) FROM candlesticks WHERE symbol = ?", [symbol.upper()]
        ).fetchone()[0]
        conn.execute("DELETE FROM candlesticks WHERE symbol = ?", [symbol.upper()])
    else:
        count = conn.execute(
            "SELECT COUNT(*) FROM candlesticks WHERE timeframe = ?", [timeframe]
        ).fetchone()[0]
        conn.execute("DELETE FROM candlesticks WHERE timeframe = ?", [timeframe])

    if own_conn:
        conn.close()
    return int(count)


def list_symbols(
    timeframe: str | None = None,
    conn: duckdb.DuckDBPyConnection | None = None,
) -> list[str]:
    """Return distinct symbols in the database, optionally filtered by timeframe."""
    own_conn = conn is None
    if own_conn:
        conn = get_connection()

    if timeframe:
        rows = conn.execute(
            "SELECT DISTINCT symbol FROM candlesticks WHERE timeframe = ? ORDER BY symbol",
            [timeframe],
        ).fetchall()
    else:
        rows = conn.execute(
            "SELECT DISTINCT symbol FROM candlesticks ORDER BY symbol"
        ).fetchall()

    if own_conn:
        conn.close()
    return [row[0] for row in rows]
