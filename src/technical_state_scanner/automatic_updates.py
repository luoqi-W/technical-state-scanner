"""Background K-line update scheduler for the API server."""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from datetime import datetime, time
from typing import Any
from zoneinfo import ZoneInfo

from technical_state_scanner.core.scanner import load_named_universe, load_symbols_from_file
from technical_state_scanner.history_downloader import download_history_for_symbols

logger = logging.getLogger("scanner.auto_updates")

NEW_YORK_TZ = ZoneInfo("America/New_York")
US_PRE_MARKET_START = time(4, 0)
US_REGULAR_OPEN = time(9, 30)
US_REGULAR_CLOSE = time(16, 0)
US_EXTENDED_CLOSE = time(20, 0)


@dataclass(frozen=True)
class AutoUpdatePhase:
    name: str
    timeframes: list[str]
    mode: str
    interval_seconds: int | None = None
    max_pages: int = 1


DEFAULT_AUTO_UPDATE_PHASES = [
    AutoUpdatePhase("pre_market", ["daily", "weekly"], "once_per_day"),
    AutoUpdatePhase("intraday", ["15min", "4hour"], "interval", interval_seconds=5 * 60),
    AutoUpdatePhase("post_market", ["daily", "weekly"], "once_per_day"),
]


def resolve_auto_update_symbols(universe: str = "watchlist") -> list[str]:
    try:
        return load_named_universe(universe)
    except (FileNotFoundError, ValueError):
        return load_symbols_from_file(universe)


def _now_et(now: datetime | None = None) -> datetime:
    current = now or datetime.now(tz=NEW_YORK_TZ)
    if current.tzinfo is None:
        current = current.replace(tzinfo=NEW_YORK_TZ)
    return current.astimezone(NEW_YORK_TZ)


def is_us_weekday(now: datetime | None = None) -> bool:
    return _now_et(now).weekday() < 5


def is_pre_market_window(now: datetime | None = None) -> bool:
    current = _now_et(now)
    return is_us_weekday(current) and US_PRE_MARKET_START <= current.time() < US_REGULAR_OPEN


def is_intraday_window(now: datetime | None = None) -> bool:
    current = _now_et(now)
    # Match StockSelection: refresh 15m/4h during US pre-market through after-hours.
    return is_us_weekday(current) and US_PRE_MARKET_START <= current.time() <= US_EXTENDED_CLOSE


def is_post_market_window(now: datetime | None = None) -> bool:
    current = _now_et(now)
    return is_us_weekday(current) and US_REGULAR_CLOSE <= current.time() <= US_EXTENDED_CLOSE


def phase_is_active(phase_name: str, now: datetime | None = None) -> bool:
    if phase_name == "pre_market":
        return is_pre_market_window(now)
    if phase_name == "intraday":
        return is_intraday_window(now)
    if phase_name == "post_market":
        return is_post_market_window(now)
    raise ValueError(f"Unknown auto update phase: {phase_name}")


class AutoKlineUpdater:
    """Runs StockSelection-style K-line updates in a single background queue."""

    def __init__(
        self,
        universe: str = "watchlist",
        phases: list[AutoUpdatePhase] | None = None,
        check_interval_seconds: int = 60,
    ):
        self.universe = universe
        self.phases = phases or DEFAULT_AUTO_UPDATE_PHASES
        self.check_interval_seconds = check_interval_seconds
        self._tasks: list[asyncio.Task[Any]] = []
        self._stop_event: asyncio.Event | None = None
        self._last_run_at: dict[str, float] = {}
        self._last_once_per_day_run: dict[str, str] = {}

    async def start(self) -> None:
        if self._tasks:
            return
        self._stop_event = asyncio.Event()
        symbols = resolve_auto_update_symbols(self.universe)
        task = asyncio.create_task(self._run_phases(symbols), name="kline-auto-updates")
        self._tasks.append(task)
        logger.info("Started automatic K-line updates for %s symbols.", len(symbols))

    async def stop(self) -> None:
        if self._stop_event is not None:
            self._stop_event.set()
        for task in self._tasks:
            task.cancel()
        if self._tasks:
            await asyncio.gather(*self._tasks, return_exceptions=True)
        self._tasks = []
        self._stop_event = None

    def _phase_due(self, phase: AutoUpdatePhase, now_et: datetime, loop_time: float) -> bool:
        if not phase_is_active(phase.name, now_et):
            return False

        if phase.mode == "once_per_day":
            run_key = now_et.date().isoformat()
            return self._last_once_per_day_run.get(phase.name) != run_key

        if phase.mode == "interval":
            last_run = self._last_run_at.get(phase.name)
            return last_run is None or (loop_time - last_run) >= (phase.interval_seconds or 0)

        raise ValueError(f"Unknown auto update mode: {phase.mode}")

    def _mark_phase_run(self, phase: AutoUpdatePhase, now_et: datetime, loop_time: float) -> None:
        self._last_run_at[phase.name] = loop_time
        if phase.mode == "once_per_day":
            self._last_once_per_day_run[phase.name] = now_et.date().isoformat()

    async def _run_phases(self, symbols: list[str]) -> None:
        assert self._stop_event is not None
        while not self._stop_event.is_set():
            loop = asyncio.get_running_loop()
            loop_time = loop.time()
            now_et = _now_et()
            due_phases = [
                phase for phase in self.phases
                if self._phase_due(phase, now_et, loop_time)
            ]

            for phase in due_phases:
                if self._stop_event.is_set():
                    break
                started = datetime.now(tz=NEW_YORK_TZ)
                try:
                    batch = await asyncio.to_thread(
                        download_history_for_symbols,
                        symbols,
                        phase.timeframes,
                        phase.max_pages,
                    )
                    logger.info(
                        "Auto K-line phase %s complete: started_et=%s symbols=%s rows=%s errors=%s",
                        phase.name,
                        started.isoformat(),
                        batch.symbols_processed,
                        batch.rows_written,
                        len(batch.errors),
                    )
                    if batch.errors:
                        logger.warning("Auto K-line phase %s sample errors: %s", phase.name, batch.errors[:5])
                except asyncio.CancelledError:
                    raise
                except Exception as exc:
                    logger.exception("Auto K-line phase %s failed: %s", phase.name, exc)
                finally:
                    self._mark_phase_run(phase, now_et, loop.time())

            try:
                await asyncio.wait_for(self._stop_event.wait(), timeout=self.check_interval_seconds)
            except asyncio.TimeoutError:
                continue
