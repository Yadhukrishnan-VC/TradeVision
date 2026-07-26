from __future__ import annotations

import logging
import signal
import time
from collections.abc import Callable
from datetime import datetime, timedelta
from threading import Event, Lock, Thread
from typing import Any

from apps.market_data.application.ports import TickSource
from apps.market_data.domain.entities import Quote
from core.market_calendar import MarketSession, get_market_calendar
from core.redis_client import get_redis_client
from core.utils import get_ist_now

logger = logging.getLogger(__name__)

_RECONNECT_DELAYS: list[int] = [1, 2, 4, 8, 16, 30]
_MAX_BACKOFF_DELAY: int = 30
_STATE_KEY: str = "market_data:websocket:state"
_PRE_MARKET_BUFFER_MINUTES: int = 5


class WebSocketTickManager:
    """Manages the lifecycle of a real-time tick streaming connection.

    Responsibilities:
        - Start and stop the ``TickSource`` adapter.
        - Exponential backoff reconnection during market hours.
        - Pause/resume outside market hours.
        - Flush in-flight 1-minute buckets on graceful shutdown.
        - Expose connection state for health endpoint.

    The manager is designed to run as a long-lived background service
    within the Django / Celery worker process.

    Args:
        tick_source:     A ``TickSource``-conforming adapter.
        on_tick:         Callback invoked on each parsed ``Quote``.
        state_key:       Redis key for storing connection state.
    """

    def __init__(
        self,
        tick_source: TickSource,
        on_tick: Callable[[Quote], None] | None = None,
        state_key: str = _STATE_KEY,
    ) -> None:
        self._tick_source = tick_source
        self._on_tick = on_tick
        self._state_key = state_key
        self._redis = get_redis_client()
        self._calendar = get_market_calendar()

        self._running = Event()
        self._lock = Lock()
        self._reconnect_attempt: int = 0
        self._shutdown_triggered: bool = False
        self._worker_thread: Thread | None = None

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def start(self) -> None:
        """Start the tick manager.

        Spawns a background worker thread that manages the connection
        lifecycle and reconnection logic.
        """
        if self._running.is_set():
            logger.warning("websocket_manager_already_running")
            return

        self._running.set()
        self._shutdown_triggered = False
        self._update_state("connecting")

        self._worker_thread = Thread(
            target=self._run_loop,
            name="websocket-manager",
            daemon=True,
        )
        self._worker_thread.start()

        logger.info("websocket_manager_started")

    def stop(self) -> None:
        """Stop the tick manager gracefully.

        Flushes in-flight data, disconnects the tick source, and waits
        for the worker thread to exit.
        """
        self._shutdown_triggered = True
        self._running.clear()
        self._update_state("disconnected")

        try:
            self._tick_source.stop()
        except Exception as exc:
            logger.warning(
                "websocket_manager_stop_error",
                extra={"error": str(exc)},
            )

        if self._worker_thread and self._worker_thread.is_alive():
            self._worker_thread.join(timeout=5)

        self._flush_before_shutdown()
        logger.info("websocket_manager_stopped")

    @property
    def is_running(self) -> bool:
        """Return ``True`` if the manager is active."""
        return self._running.is_set()

    @property
    def connection_state(self) -> str:
        """Return the current connection state for health checks."""
        try:
            state = self._redis.get(self._state_key)
            return state.decode() if isinstance(state, bytes) else (state or "disconnected")
        except Exception:
            return "unknown"

    def subscribe(self, instruments: list[int]) -> None:
        """Subscribe to ticks for the given instrument tokens."""
        self._tick_source.subscribe(instruments)

    def unsubscribe(self, instruments: list[int]) -> None:
        """Unsubscribe from ticks for the given instrument tokens."""
        self._tick_source.unsubscribe(instruments)

    # ------------------------------------------------------------------
    # Internal lifecycle
    # ------------------------------------------------------------------

    def _run_loop(self) -> None:
        """Main loop: manages connection lifecycle respecting market sessions."""
        try:
            while self._running.is_set() and not self._shutdown_triggered:
                session = self._calendar.get_session(get_ist_now())

                if self._should_pause(session):
                    self._pause_until_next_session()
                    continue

                if not self._tick_source.is_connected:
                    self._attempt_reconnect()
                else:
                    self._reconnect_attempt = 0
                    self._update_state("connected")

                time.sleep(1)
        except Exception as exc:
            logger.error(
                "websocket_manager_loop_crashed",
                extra={"error": str(exc)},
                exc_info=True,
            )
            self._update_state("disconnected")

    def _should_pause(self, session: MarketSession) -> bool:
        """Return ``True`` if the tick source should be paused."""
        if self._shutdown_triggered:
            return True

        if session in (MarketSession.CLOSED, MarketSession.HOLIDAY):
            return True

        if session == MarketSession.POST_MARKET:
            return True

        return False

    def _pause_until_next_session(self) -> None:
        """Disconnect and wait until near the next market open."""
        self._update_state("paused")
        if self._tick_source.is_connected:
            try:
                self._tick_source.stop()
            except Exception as exc:
                logger.warning(
                    "websocket_manager_pause_stop_error",
                    extra={"error": str(exc)},
                )

        seconds_to_open = self._calendar.seconds_to_market_open(get_ist_now())
        sleep_seconds = max(seconds_to_open - _PRE_MARKET_BUFFER_MINUTES * 60, 10)
        logger.info(
            "websocket_manager_paused",
            extra={"seconds_until_resume": sleep_seconds},
        )
        self._running.wait(timeout=sleep_seconds)

    def _attempt_reconnect(self) -> None:
        """Attempt to reconnect the tick source with exponential backoff."""
        delay = self._get_backoff_delay()
        self._update_state("connecting")

        logger.info(
            "websocket_manager_reconnecting",
            extra={
                "attempt": self._reconnect_attempt + 1,
                "delay_seconds": delay,
            },
        )

        self._running.wait(timeout=delay)

        if not self._running.is_set():
            return

        try:
            self._tick_source.start(on_tick=self._on_tick_callback)
            self._reconnect_attempt = 0
            self._update_state("connected")
            logger.info("websocket_manager_connected")
        except Exception as exc:
            self._reconnect_attempt += 1
            self._update_state("degraded")
            logger.error(
                "websocket_manager_reconnect_failed",
                extra={
                    "attempt": self._reconnect_attempt,
                    "error": str(exc),
                },
            )

    def _get_backoff_delay(self) -> int:
        """Calculate the next backoff delay based on attempt count.

        Uses exponential backoff: 1, 2, 4, 8, 16, 30, 30, ...
        """
        if self._reconnect_attempt < len(_RECONNECT_DELAYS):
            return _RECONNECT_DELAYS[self._reconnect_attempt]
        return _MAX_BACKOFF_DELAY

    def _on_tick_callback(self, quote: Quote) -> None:
        """Handle an incoming tick.

        Updates the Redis state key and forwards to the registered
        callback.
        """
        self._update_state("connected")
        if self._on_tick is not None:
            try:
                self._on_tick(quote)
            except Exception as exc:
                logger.error(
                    "websocket_manager_tick_handler_error",
                    extra={"error": str(exc)},
                )

    def _update_state(self, state: str) -> None:
        """Update the Redis connection state key."""
        try:
            self._redis.set(self._state_key, state)
        except Exception as exc:
            logger.warning(
                "websocket_manager_state_update_failed",
                extra={"error": str(exc)},
            )

    def _flush_before_shutdown(self) -> None:
        """Flush in-flight data before shutdown.

        Override this in production to persist any in-memory candle
        buckets before the process exits.
        """
        logger.info("websocket_manager_flush_before_shutdown")

    # ------------------------------------------------------------------
    # Signal handling (install at application startup)
    # ------------------------------------------------------------------

    @classmethod
    def install_signal_handlers(cls, manager: WebSocketTickManager) -> None:
        """Install graceful shutdown handlers for SIGTERM and SIGINT.

        Call during ``AppConfig.ready()`` or at process startup.
        """
        def _handler(signum: int, frame: Any) -> None:
            logger.info("websocket_manager_signal_received", extra={"signal": signum})
            manager.stop()

        signal.signal(signal.SIGTERM, _handler)
        signal.signal(signal.SIGINT, _handler)
