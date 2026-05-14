from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import inspect

import pandas as pd

from technical_state_scanner.loader import _load_candles_raw, normalize_candles_to_ohlcv, normalize_symbol, resample_ohlcv


@dataclass
class CandleStub:
    timestamp: datetime
    open: float
    high: float
    low: float
    close: float
    volume: float


def _assert_ohlcv_schema(frame: pd.DataFrame) -> None:
    assert isinstance(frame.index, pd.DatetimeIndex)
    assert frame.index.tz is not None
    assert list(frame.columns) == ["Open", "High", "Low", "Close", "Volume"]


def test_normalize_symbol_appends_us_suffix_for_plain_ticker():
    assert normalize_symbol("AAPL") == "AAPL.US"


def test_normalize_symbol_preserves_market_qualified_ticker():
    assert normalize_symbol("crcl.us") == "CRCL.US"


def test_weekly_daily_4hour_ohlcv_schema_from_daily_resampling():
    candles = [
        CandleStub(datetime(2026, 1, 5, tzinfo=timezone.utc), 10, 11, 9, 10.5, 1000),
        CandleStub(datetime(2026, 1, 6, tzinfo=timezone.utc), 10.5, 12, 10, 11.5, 1500),
        CandleStub(datetime(2026, 1, 7, tzinfo=timezone.utc), 11.5, 13, 11, 12.5, 1800),
        CandleStub(datetime(2026, 1, 8, tzinfo=timezone.utc), 12.5, 14, 12, 13.2, 2000),
    ]
    daily = normalize_candles_to_ohlcv(candles)
    weekly = resample_ohlcv(daily, "W-MON", now_utc=datetime(2026, 1, 20, tzinfo=timezone.utc))

    h4_source = pd.DataFrame(
        {
            "Open": [10, 11, 12, 13],
            "High": [11, 12, 13, 14],
            "Low": [9, 10, 11, 12],
            "Close": [10.5, 11.5, 12.5, 13.5],
            "Volume": [100, 120, 130, 140],
        },
        index=pd.DatetimeIndex(
            [
                datetime(2026, 1, 5, 0, 0, tzinfo=timezone.utc),
                datetime(2026, 1, 5, 1, 0, tzinfo=timezone.utc),
                datetime(2026, 1, 5, 2, 0, tzinfo=timezone.utc),
                datetime(2026, 1, 5, 3, 0, tzinfo=timezone.utc),
            ]
        ),
    )
    h4 = resample_ohlcv(h4_source, "4h", now_utc=datetime(2026, 1, 6, tzinfo=timezone.utc))

    _assert_ohlcv_schema(weekly)
    _assert_ohlcv_schema(daily)
    _assert_ohlcv_schema(h4)


def test_longport_candlesticks_count_is_integer_and_adjust_type_is_separate():
    class ContextStub:
        def __init__(self):
            self.calls = []

        def candlesticks(self, symbol, period, count, adjust_type, trade_sessions=None):
            self.calls.append(
                {
                    "symbol": symbol,
                    "period": period,
                    "count": count,
                    "adjust_type": adjust_type,
                    "trade_sessions": trade_sessions,
                }
            )
            return [
                CandleStub(datetime(2026, 1, 5, tzinfo=timezone.utc), 10, 11, 9, 10.5, 1000)
            ]

    ctx = ContextStub()
    frame = _load_candles_raw(ctx, period_value="Day", symbol="AAPL.US", count=300)

    call = ctx.calls[0]
    assert call["count"] == 300
    assert isinstance(call["count"], int)
    assert "AdjustType" not in type(call["count"]).__name__
    assert "AdjustType" in type(call["adjust_type"]).__name__
    _assert_ohlcv_schema(frame)


def test_longport_candlesticks_positional_fallback_preserves_count_position():
    signature = inspect.Signature(
        parameters=[
            inspect.Parameter("symbol", inspect.Parameter.POSITIONAL_OR_KEYWORD),
            inspect.Parameter("period", inspect.Parameter.POSITIONAL_OR_KEYWORD),
            inspect.Parameter("count", inspect.Parameter.POSITIONAL_OR_KEYWORD),
            inspect.Parameter("adjust_type", inspect.Parameter.POSITIONAL_OR_KEYWORD),
            inspect.Parameter("trade_sessions", inspect.Parameter.POSITIONAL_OR_KEYWORD, default=None),
        ]
    )

    class CandlesticksCallable:
        __signature__ = signature

        def __init__(self):
            self.calls = []

        def __call__(self, *args, **kwargs):
            if kwargs:
                raise TypeError("keywords are unsupported by this SDK build")
            self.calls.append(args)
            return [
                CandleStub(datetime(2026, 1, 5, tzinfo=timezone.utc), 10, 11, 9, 10.5, 1000)
            ]

    class PositionalOnlyContextStub:
        def __init__(self):
            self.candlesticks = CandlesticksCallable()

    ctx = PositionalOnlyContextStub()
    _load_candles_raw(ctx, period_value="Day", symbol="AAPL.US", count=700)

    _symbol, _period, count, adjust_type, _trade_sessions = ctx.candlesticks.calls[0]
    assert count == 700
    assert isinstance(count, int)
    assert "AdjustType" not in type(count).__name__
    assert "AdjustType" in type(adjust_type).__name__
