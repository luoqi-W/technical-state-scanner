"""Daily scheduling engine for automated data fetching.

Implements the four-phase scheduling cycle described in the design document:

| Phase        | Timing                       | Task                                      |
|-------------|------------------------------|-------------------------------------------|
| pre-market  | 4:00-9:30 AM ET              | Supplement daily + weekly K-line           |
| intraday    | 4:00 AM-8:00 PM ET           | 15m / 4h rolling incremental update        |
| post-market | 4:00-8:00 PM ET              | Finalize daily + weekly K-line             |

Data is pulled in batches per watchlist symbol to avoid triggering LongPort API
rate limits.
"""

from __future__ import annotations

import asyncio
import logging
import sys
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from enum import Enum
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from technical_state_scanner.history_downloader import (
    LongPortHistoryRateLimiter,
    download_history_for_symbol_timeframe,
)
from technical_state_scanner.loader import _create_longport_quote_context, normalize_symbol

logger = logging.getLogger("scanner.scheduler")


class SchedulePhase(str, Enum):
    PRE_MARKET = "pre_market"
    INTRADAY = "intraday"
    POST_MARKET = "post_market"
    WEEKLY = "weekly"


@dataclass
class SchedulerConfig:
    """Configuration for the scheduler."""

    symbols: list[str] = field(default_factory=list)
    intraday_interval_seconds: int = 300
    batch_size: int = 5
    batch_delay_seconds: float = 1.0
    pre_market_daily_count: int = 30
    pre_market_weekly_count: int = 30
    intraday_15m_count: int = 30
    intraday_4h_count: int = 30
    post_market_daily_count: int = 30
    post_market_weekly_count: int = 30
    weekly_count: int = 30


@dataclass
class PhaseResult:
    """Result of a single scheduler phase execution."""

    phase: SchedulePhase
    started_at: datetime
    finished_at: datetime
    symbols_processed: int
    symbols_failed: int
    rows_written: int
    errors: list[str] = field(default_factory=list)


def _log(message: str) -> None:
    logger.info(message)
    print(f"[scheduler] {message}", file=sys.stderr)


def _fetch_and_store(
    symbol: str,
    timeframe: str,
    count: int,
    ctx: Any,
    rate_limiter: LongPortHistoryRateLimiter | None = None,
) -> int:
    """Fetch historical candles from LongPort and upsert into DuckDB.

    Scheduler phases are incremental, so one 1000-bar history page is enough to
    catch normal daily gaps while respecting LongPort's history API limits.
    """
    normalized = normalize_symbol(symbol)
    result = download_history_for_symbol_timeframe(
        normalized,
        timeframe,
        ctx=ctx,
        max_pages=1,
        rate_limiter=rate_limiter,
    )
    if result.error:
        raise RuntimeError(result.error)
    return result.rows_written


def _run_phase_for_symbols(
    symbols: list[str],
    timeframes_and_counts: list[tuple[str, int]],
    phase: SchedulePhase,
    config: SchedulerConfig,
    on_progress: Callable[[str, str], None] | None = None,
) -> PhaseResult:
    """Execute a phase: fetch specified timeframes for all symbols in batches."""
    started = datetime.now(timezone.utc)
    total_rows = 0
    failed = 0
    errors: list[str] = []

    ctx = _create_longport_quote_context()
    rate_limiter = LongPortHistoryRateLimiter()

    for batch_start in range(0, len(symbols), config.batch_size):
        batch = symbols[batch_start : batch_start + config.batch_size]
        for symbol in batch:
            for timeframe, count in timeframes_and_counts:
                try:
                    rows = _fetch_and_store(symbol, timeframe, count, ctx, rate_limiter=rate_limiter)
                    total_rows += rows
                    if on_progress:
                        on_progress(symbol, timeframe)
                except Exception as exc:
                    failed += 1
                    msg = f"{symbol}/{timeframe}: {exc}"
                    errors.append(msg)
                    _log(f"ERROR {msg}")
        if batch_start + config.batch_size < len(symbols):
            time.sleep(config.batch_delay_seconds)

    return PhaseResult(
        phase=phase,
        started_at=started,
        finished_at=datetime.now(timezone.utc),
        symbols_processed=len(symbols),
        symbols_failed=failed,
        rows_written=total_rows,
        errors=errors,
    )


def run_pre_market(
    config: SchedulerConfig,
    on_progress: Callable[[str, str], None] | None = None,
) -> PhaseResult:
    """Pre-market phase: supplement daily and weekly K-line data."""
    _log(f"PRE_MARKET: updating daily/weekly data for {len(config.symbols)} symbols")
    return _run_phase_for_symbols(
        symbols=config.symbols,
        timeframes_and_counts=[
            ("daily", config.pre_market_daily_count),
            ("weekly", config.pre_market_weekly_count),
        ],
        phase=SchedulePhase.PRE_MARKET,
        config=config,
        on_progress=on_progress,
    )


def run_intraday(
    config: SchedulerConfig,
    on_progress: Callable[[str, str], None] | None = None,
) -> PhaseResult:
    """Intraday phase: rolling 15m and 4h incremental update."""
    _log(f"INTRADAY: updating 15m/4h data for {len(config.symbols)} symbols")
    return _run_phase_for_symbols(
        symbols=config.symbols,
        timeframes_and_counts=[
            ("15min", config.intraday_15m_count),
            ("4hour", config.intraday_4h_count),
        ],
        phase=SchedulePhase.INTRADAY,
        config=config,
        on_progress=on_progress,
    )


def run_post_market(
    config: SchedulerConfig,
    on_progress: Callable[[str, str], None] | None = None,
) -> PhaseResult:
    """Post-market phase: finalize daily and weekly K-line data."""
    _log(f"POST_MARKET: finalizing daily/weekly for {len(config.symbols)} symbols")
    return _run_phase_for_symbols(
        symbols=config.symbols,
        timeframes_and_counts=[
            ("daily", config.post_market_daily_count),
            ("weekly", config.post_market_weekly_count),
        ],
        phase=SchedulePhase.POST_MARKET,
        config=config,
        on_progress=on_progress,
    )


def run_weekly(
    config: SchedulerConfig,
    on_progress: Callable[[str, str], None] | None = None,
) -> PhaseResult:
    """Weekly phase: update weekly K-line after Friday close."""
    _log(f"WEEKLY: updating weekly data for {len(config.symbols)} symbols")
    return _run_phase_for_symbols(
        symbols=config.symbols,
        timeframes_and_counts=[("weekly", config.weekly_count)],
        phase=SchedulePhase.WEEKLY,
        config=config,
        on_progress=on_progress,
    )


NEW_YORK_TZ = ZoneInfo("America/New_York")


def _to_et(now: datetime | None = None) -> datetime:
    current = now or datetime.now(tz=NEW_YORK_TZ)
    if current.tzinfo is None:
        current = current.replace(tzinfo=NEW_YORK_TZ)
    return current.astimezone(NEW_YORK_TZ)


def determine_current_phase(now: datetime | None = None) -> SchedulePhase | None:
    """Determine which scheduler phase should run based on current ET time.

    Returns None outside of any scheduled window.
    """
    now_et = _to_et(now)
    weekday = now_et.weekday()  # 0=Monday, 6=Sunday
    minutes = now_et.hour * 60 + now_et.minute

    if weekday >= 5:
        return None

    pre_market_start = 4 * 60
    regular_open = 9 * 60 + 30
    regular_close = 16 * 60
    extended_close = 20 * 60

    if pre_market_start <= minutes < regular_open:
        return SchedulePhase.PRE_MARKET
    if regular_open <= minutes < regular_close:
        return SchedulePhase.INTRADAY
    if regular_close <= minutes <= extended_close:
        return SchedulePhase.POST_MARKET

    return None


PHASE_RUNNERS = {
    SchedulePhase.PRE_MARKET: run_pre_market,
    SchedulePhase.INTRADAY: run_intraday,
    SchedulePhase.POST_MARKET: run_post_market,
    SchedulePhase.WEEKLY: run_weekly,
}


def run_phase(
    phase: SchedulePhase,
    config: SchedulerConfig,
    on_progress: Callable[[str, str], None] | None = None,
) -> PhaseResult:
    """Run a specific scheduler phase."""
    runner = PHASE_RUNNERS[phase]
    return runner(config, on_progress=on_progress)


def run_auto(
    config: SchedulerConfig,
    on_progress: Callable[[str, str], None] | None = None,
) -> PhaseResult | None:
    """Determine and run the appropriate phase for the current time."""
    phase = determine_current_phase()
    if phase is None:
        _log("No scheduled phase for the current time window.")
        return None
    return run_phase(phase, config, on_progress=on_progress)


class SchedulerLoop:
    """Long-running scheduler loop that automatically executes phases based on time.

    The loop checks the current phase every ``check_interval_seconds`` and runs
    it if it hasn't already been run in the current window.
    """

    def __init__(self, config: SchedulerConfig, check_interval_seconds: int = 60):
        self.config = config
        self.check_interval = check_interval_seconds
        self._last_phase_run: dict[SchedulePhase, datetime] = {}
        self._running = False

    def _should_run(self, phase: SchedulePhase) -> bool:
        last = self._last_phase_run.get(phase)
        if last is None:
            return True
        now = datetime.now(timezone.utc)
        if phase == SchedulePhase.INTRADAY:
            return (now - last).total_seconds() >= self.config.intraday_interval_seconds
        return _to_et(now).date() != _to_et(last).date()

    def run_forever(self) -> None:
        """Block the current thread and run the scheduler loop indefinitely."""
        self._running = True
        _log("Scheduler loop started.")
        while self._running:
            phase = determine_current_phase()
            if phase is not None and self._should_run(phase):
                _log(f"Running phase: {phase.value}")
                try:
                    result = run_phase(phase, self.config)
                    self._last_phase_run[phase] = datetime.now(timezone.utc)
                    _log(
                        f"Phase {phase.value} complete: "
                        f"{result.symbols_processed} symbols, "
                        f"{result.rows_written} rows, "
                        f"{result.symbols_failed} failed"
                    )
                except Exception as exc:
                    _log(f"Phase {phase.value} error: {exc}")
            time.sleep(self.check_interval)

    def stop(self) -> None:
        self._running = False
        _log("Scheduler loop stopping.")
