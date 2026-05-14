from __future__ import annotations

import pandas as pd

from technical_state_scanner.loader import load_multi_timeframe_ohlcv


def main() -> int:
    symbol = "AAPL.US"
    try:
        frames, statuses = load_multi_timeframe_ohlcv(symbol=symbol, count=700)
    except Exception as exc:
        print(f"Failed to load LongPort candlestick data for {symbol}: {exc}")
        return 1

    for timeframe in ["weekly", "daily", "4hour"]:
        frame = frames[timeframe]
        status = statuses[timeframe]
        latest = frame.index.max().isoformat() if not frame.empty else "N/A"
        print(f"{timeframe}: shape={frame.shape}, latest={latest}, status={status.reason or 'ok'}")
        diag = frame[["Close", "EMA12", "EMA144", "EMA169", "EMA576", "EMA676"]].tail(3)
        print(diag.to_string())
        print()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
