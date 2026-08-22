"""FastAPI application: REST API for stock pool / scoring / K-line history,
plus a WebSocket gateway for real-time intraday push.
"""

from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException, Query, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from technical_state_scanner.api.ws_manager import ConnectionManager
from technical_state_scanner.automatic_updates import AutoKlineUpdater, DEFAULT_AUTO_UPDATE_PHASES
from technical_state_scanner.core.csv_output import scan_result_to_structured_output
from technical_state_scanner.core.scanner import (
    ScanResult,
    load_named_universe,
    load_symbols_from_file,
    scan_symbol,
    scan_symbol_smart,
    scan_universe_concurrent,
)
from technical_state_scanner.db.duckdb_store import (
    get_bar_count,
    get_connection,
    get_latest_timestamp,
    list_symbols,
    read_candles,
)
from technical_state_scanner.loader import normalize_symbol
from technical_state_scanner.scheduler.scheduler import (
    SchedulePhase,
    SchedulerConfig,
    SchedulerLoop,
    run_phase,
)

ws_manager = ConnectionManager()

_scheduler_loop: SchedulerLoop | None = None
_scheduler_task: asyncio.Task | None = None
_auto_kline_updater: AutoKlineUpdater | None = None


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    global _scheduler_loop, _scheduler_task, _auto_kline_updater
    _auto_kline_updater = AutoKlineUpdater()
    await _auto_kline_updater.start()
    try:
        yield
    finally:
        if _auto_kline_updater is not None:
            await _auto_kline_updater.stop()
            _auto_kline_updater = None
    if _scheduler_loop is not None:
        _scheduler_loop.stop()
    if _scheduler_task is not None:
        _scheduler_task.cancel()


app = FastAPI(
    title="Technical State Scanner API",
    description="REST API for stock pool, scoring, and K-line history; WebSocket for real-time intraday push.",
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

FRONTEND_DIST = Path(__file__).resolve().parents[3] / "frontend" / "dist"


# ─── REST endpoints ─────────────────────────────────────────────────────────


@app.get("/api/health")
async def health() -> dict[str, str]:
    return {"status": "ok", "timestamp": datetime.now(timezone.utc).isoformat()}


@app.get("/api/kline/auto-update/status")
async def get_auto_update_status() -> dict[str, Any]:
    """Return automatic K-line update loop configuration."""

    return {
        "enabled": _auto_kline_updater is not None,
        "universe": _auto_kline_updater.universe if _auto_kline_updater is not None else "watchlist",
        "phases": [
            {
                "name": phase.name,
                "timeframes": phase.timeframes,
                "mode": phase.mode,
                "interval_seconds": phase.interval_seconds,
                "max_pages": phase.max_pages,
            }
            for phase in DEFAULT_AUTO_UPDATE_PHASES
        ],
    }


# ── Stock Pool ───────────────────────────────────────────────────────────────


@app.get("/api/pool/symbols")
async def get_pool_symbols(
    universe: str = Query("watchlist", description="Universe name or file path"),
) -> dict[str, Any]:
    """Return the list of symbols in a stock pool / universe."""
    try:
        symbols = load_named_universe(universe)
    except (FileNotFoundError, ValueError):
        try:
            symbols = load_symbols_from_file(universe)
        except Exception as exc:
            raise HTTPException(status_code=400, detail=str(exc))
    return {"universe": universe, "count": len(symbols), "symbols": symbols}


@app.get("/api/pool/scan")
async def scan_pool(
    universe: str = Query("watchlist"),
    count: int = Query(700, ge=100, le=2000),
    workers: int = Query(3, ge=1, le=8),
    force_refresh: bool = Query(False),
) -> dict[str, Any]:
    """Scan an entire stock pool and return ranked results."""
    try:
        symbols = load_named_universe(universe)
    except (FileNotFoundError, ValueError):
        try:
            symbols = load_symbols_from_file(universe)
        except Exception as exc:
            raise HTTPException(status_code=400, detail=str(exc))

    results = scan_universe_concurrent(
        symbols=symbols,
        count=count,
        max_workers=workers,
        force_refresh=force_refresh,
    )

    ranked = []
    for r in results:
        ranked.append({
            "ticker": r.ticker,
            "total_score": r.total_score,
            "pre_multiplier_score": r.pre_multiplier_score,
            "all_triggered_signals": r.all_triggered_signals,
            "error": r.error,
        })
    return {"universe": universe, "count": len(ranked), "results": ranked}


# ── Scoring ──────────────────────────────────────────────────────────────────


@app.get("/api/score/{symbol}")
async def get_score(
    symbol: str,
    count: int = Query(700, ge=100, le=2000),
    force_refresh: bool = Query(False),
) -> dict[str, Any]:
    """Run a full multi-timeframe scan for a single symbol and return detailed scoring."""
    try:
        if force_refresh:
            result = scan_symbol(symbol, count=count)
        else:
            result = scan_symbol_smart(symbol, count=count, force_refresh=force_refresh)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))
    return scan_result_to_structured_output(result)


# ── K-line History ───────────────────────────────────────────────────────────


@app.get("/api/kline/{symbol}")
async def get_kline(
    symbol: str,
    timeframe: str = Query("daily", description="Timeframe: weekly, daily, 4hour, 15min"),
    limit: int = Query(300, ge=1, le=2000),
) -> dict[str, Any]:
    """Return historical K-line data from the DuckDB store."""
    normalized = normalize_symbol(symbol)
    try:
        df = read_candles(normalized, timeframe, limit=limit)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))

    if df.empty:
        return {"symbol": normalized, "timeframe": timeframe, "count": 0, "candles": []}

    candles = []
    for ts, row in df.iterrows():
        candles.append({
            "timestamp": ts.isoformat(),
            "open": float(row["Open"]),
            "high": float(row["High"]),
            "low": float(row["Low"]),
            "close": float(row["Close"]),
            "volume": float(row["Volume"]),
        })
    return {
        "symbol": normalized,
        "timeframe": timeframe,
        "count": len(candles),
        "candles": candles,
    }


@app.get("/api/kline/{symbol}/indicators")
async def get_kline_with_indicators(
    symbol: str,
    timeframe: str = Query("daily"),
    limit: int = Query(300, ge=1, le=2000),
) -> dict[str, Any]:
    """Return K-line data with EMA indicator overlays computed on the fly."""
    from technical_state_scanner.core.indicators import add_vegas_tunnel_columns

    normalized = normalize_symbol(symbol)
    try:
        df = read_candles(normalized, timeframe)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))

    if df.empty:
        return {"symbol": normalized, "timeframe": timeframe, "count": 0, "candles": [], "ema": {}}

    df_with_ema, _status = add_vegas_tunnel_columns(df)
    df_tail = df_with_ema.tail(limit)

    candles = []
    ema_data = {col: [] for col in ["EMA12", "EMA144", "EMA169", "EMA576", "EMA676"]}
    for ts, row in df_tail.iterrows():
        ts_iso = ts.isoformat()
        candles.append({
            "timestamp": ts_iso,
            "open": float(row["Open"]),
            "high": float(row["High"]),
            "low": float(row["Low"]),
            "close": float(row["Close"]),
            "volume": float(row["Volume"]),
        })
        for col in ema_data:
            if col in row.index:
                val = float(row[col])
                if not (val != val):  # skip NaN
                    ema_data[col].append({"timestamp": ts_iso, "value": val})
    return {
        "symbol": normalized,
        "timeframe": timeframe,
        "count": len(candles),
        "candles": candles,
        "ema": ema_data,
    }


@app.get("/api/kline/{symbol}/metadata")
async def get_kline_metadata(symbol: str) -> dict[str, Any]:
    """Return metadata about stored K-line data for a symbol."""
    normalized = normalize_symbol(symbol)
    meta: dict[str, Any] = {}
    for tf in ["weekly", "daily", "4hour", "15min"]:
        latest = get_latest_timestamp(normalized, tf)
        count = get_bar_count(normalized, tf)
        meta[tf] = {
            "bar_count": count,
            "latest_timestamp": latest.isoformat() if latest else None,
        }
    return {"symbol": normalized, "timeframes": meta}


@app.get("/api/db/symbols")
async def get_db_symbols(
    timeframe: str | None = Query(None),
) -> dict[str, Any]:
    """List symbols in the DuckDB store."""
    symbols = list_symbols(timeframe=timeframe)
    return {"count": len(symbols), "symbols": symbols}


# ── Scheduler ────────────────────────────────────────────────────────────────


@app.post("/api/scheduler/run")
async def trigger_scheduler_phase(
    phase: str = Query(..., description="Phase: pre_market, intraday, post_market, weekly"),
    universe: str = Query("watchlist"),
) -> dict[str, Any]:
    """Manually trigger a scheduler phase."""
    try:
        phase_enum = SchedulePhase(phase)
    except ValueError:
        raise HTTPException(status_code=400, detail=f"Invalid phase: {phase}")

    try:
        symbols = load_named_universe(universe)
    except (FileNotFoundError, ValueError):
        try:
            symbols = load_symbols_from_file(universe)
        except Exception as exc:
            raise HTTPException(status_code=400, detail=str(exc))

    config = SchedulerConfig(symbols=symbols)
    result = run_phase(phase_enum, config)
    return {
        "phase": result.phase.value,
        "started_at": result.started_at.isoformat(),
        "finished_at": result.finished_at.isoformat(),
        "symbols_processed": result.symbols_processed,
        "symbols_failed": result.symbols_failed,
        "rows_written": result.rows_written,
        "errors": result.errors,
    }


# ── WebSocket gateway ────────────────────────────────────────────────────────


@app.websocket("/ws/intraday")
async def websocket_intraday(websocket: WebSocket) -> None:
    """WebSocket endpoint for real-time intraday signal push.

    After connecting, send a JSON message with ``{"subscribe": ["AAPL.US", ...]}``
    to receive updates for those symbols.  The server pushes scan results whenever
    new intraday data is processed.
    """
    await ws_manager.connect(websocket)
    try:
        while True:
            data = await websocket.receive_text()
            try:
                message = json.loads(data)
            except json.JSONDecodeError:
                await websocket.send_json({"error": "Invalid JSON"})
                continue

            if "subscribe" in message:
                symbols = message["subscribe"]
                if isinstance(symbols, list):
                    ws_manager.subscribe(websocket, symbols)
                    await websocket.send_json({
                        "status": "subscribed",
                        "symbols": symbols,
                    })

            elif "unsubscribe" in message:
                symbols = message["unsubscribe"]
                if isinstance(symbols, list):
                    ws_manager.unsubscribe(websocket, symbols)
                    await websocket.send_json({
                        "status": "unsubscribed",
                        "symbols": symbols,
                    })

            elif "scan" in message:
                symbol = message["scan"]
                try:
                    result = scan_symbol_smart(normalize_symbol(symbol), count=700)
                    output = scan_result_to_structured_output(result)
                    await websocket.send_json({"type": "scan_result", "data": output})
                except Exception as exc:
                    await websocket.send_json({"error": str(exc)})

    except WebSocketDisconnect:
        ws_manager.disconnect(websocket)


if FRONTEND_DIST.exists():
    app.mount("/", StaticFiles(directory=FRONTEND_DIST, html=True), name="frontend")


def run_server(host: str = "0.0.0.0", port: int = 8000) -> None:
    """Start the FastAPI server with uvicorn."""
    import uvicorn

    uvicorn.run(app, host=host, port=port)


if __name__ == "__main__":
    run_server()
