from __future__ import annotations

import json
import logging
import threading
from collections.abc import Callable
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any

from apps.market_data.application.ports import TickSource
from apps.market_data.domain.entities import Quote
from core.config import config

logger = logging.getLogger(__name__)

_TICK_RECONNECT_DELAYS: list[int] = [1, 2, 4, 8, 16, 30]


class ZerodhaTickerAdapter:
    """Adapter that wraps the Zerodha KiteTicker WebSocket as a ``TickSource``.

    This adapter translates KiteTicker's raw tick callbacks into
    ``Quote`` domain entities and forwards them to the caller's
    ``on_tick`` handler.

    The actual KiteTicker import is deferred so this module loads
    cleanly when the ``zerodha`` provider is not the active one.
    """

    def __init__(
        self,
        api_key: str | None = None,
        access_token: str | None = None,
    ) -> None:
        self._api_key = api_key or config.zerodha_api_key
        self._access_token = access_token or config.zerodha_access_token
        self._ticker: Any = None
        self._on_tick: Callable[[Quote], None] | None = None
        self._subscribed_tokens: list[int] = []
        self._running = False
        self._lock = threading.Lock()
        self._connection_state: str = "disconnected"

    def subscribe(self, instruments: list[int]) -> None:
        """Subscribe to real-time ticks for the given instrument tokens.

        If already connected, the subscription is applied immediately.
        Otherwise tokens are queued and subscribed on connect.

        Args:
            instruments: List of exchange instrument tokens.
        """
        with self._lock:
            self._subscribed_tokens.extend(instruments)
            if self._ticker is not None and hasattr(self._ticker, "subscribe"):
                self._ticker.subscribe(instruments)

    def unsubscribe(self, instruments: list[int]) -> None:
        """Unsubscribe from ticks for the given instrument tokens.

        Args:
            instruments: List of exchange instrument tokens.
        """
        with self._lock:
            self._subscribed_tokens = [
                t for t in self._subscribed_tokens if t not in instruments
            ]
            if self._ticker is not None and hasattr(self._ticker, "unsubscribe"):
                self._ticker.unsubscribe(instruments)

    def start(self, on_tick: Callable[[Quote], None]) -> None:
        """Start the KiteTicker WebSocket connection.

        This method is non-blocking — it spawns the ticker in its own
        thread (KiteTicker's default behaviour).

        Args:
            on_tick: Callback invoked with each parsed ``Quote``.
        """
        self._on_tick = on_tick
        self._running = True
        self._connection_state = "connecting"

        try:
            from kiteconnect import KiteTicker

            self._ticker = KiteTicker(
                api_key=self._api_key,
                access_token=self._access_token,
            )

            self._ticker.on_ticks = self._on_ticks_callback
            self._ticker.on_connect = self._on_connect_callback
            self._ticker.on_close = self._on_close_callback
            self._ticker.on_error = self._on_error_callback
            self._ticker.on_reconnect = self._on_reconnect_callback
            self._ticker.on_noreconnect = self._on_noreconnect_callback

            self._ticker.connect(threaded=True)
        except ImportError:
            logger.error(
                "kiteconnect package not installed. "
                "Install with: pip install kiteconnect"
            )
            self._connection_state = "disconnected"
            raise

    def stop(self) -> None:
        """Gracefully stop the streaming connection."""
        self._running = False
        self._connection_state = "disconnected"
        if self._ticker is not None:
            try:
                self._ticker.close()
            except Exception as exc:
                logger.warning(
                    "zerodha_ticker_close_error",
                    extra={"error": str(exc)},
                )
        logger.info("zerodha_ticker_stopped")

    @property
    def is_connected(self) -> bool:
        """Return ``True`` if the ticker is currently connected."""
        return self._connection_state == "connected"

    @property
    def connection_state(self) -> str:
        """Return the current connection state string.

        Returns one of: ``connected``, ``disconnected``, ``connecting``,
        ``degraded``.
        """
        return self._connection_state

    # ------------------------------------------------------------------
    # KiteTicker callbacks
    # ------------------------------------------------------------------

    def _on_ticks_callback(self, ticks: list[dict[str, Any]], ws: Any) -> None:
        """Process raw ticks from KiteTicker.

        Args:
            ticks: List of raw tick dictionaries from KiteTicker.
            ws:    The WebSocket instance (unused, matches KiteTicker signature).
        """
        if self._on_tick is None:
            return

        for raw in ticks:
            try:
                quote = self._parse_tick(raw)
                if quote is not None:
                    self._on_tick(quote)
            except (ValueError, KeyError, TypeError) as exc:
                logger.warning(
                    "zerodha_tick_parse_error",
                    extra={"error": str(exc), "raw_tick": raw},
                )

    def _on_connect_callback(self, ws: Any) -> None:
        """Handle successful WebSocket connection.

        Resubscribes to any tokens that were queued before connection.
        """
        self._connection_state = "connected"
        logger.info("zerodha_ticker_connected")

        with self._lock:
            if self._subscribed_tokens and hasattr(self._ticker, "subscribe"):
                self._ticker.subscribe(self._subscribed_tokens)

    def _on_close_callback(self, ws: Any, code: int, reason: str | None) -> None:
        """Handle WebSocket disconnection."""
        self._connection_state = "disconnected"
        logger.info(
            "zerodha_ticker_disconnected",
            extra={"code": code, "reason": reason},
        )

    def _on_error_callback(self, ws: Any, code: int, reason: str | None) -> None:
        """Handle WebSocket errors."""
        self._connection_state = "degraded"
        logger.error(
            "zerodha_ticker_error",
            extra={"code": code, "reason": reason},
        )

    def _on_reconnect_callback(self, ws: Any, attempt_count: int) -> None:
        """Handle reconnection attempts."""
        self._connection_state = "connecting"
        delay = _TICK_RECONNECT_DELAYS[min(attempt_count - 1, len(_TICK_RECONNECT_DELAYS) - 1)]
        logger.info(
            "zerodha_ticker_reconnecting",
            extra={"attempt": attempt_count, "delay_seconds": delay},
        )

    def _on_noreconnect_callback(self, ws: Any) -> None:
        """Handle exhausted reconnection attempts."""
        self._connection_state = "disconnected"
        logger.error("zerodha_ticker_reconnect_exhausted")

    @staticmethod
    def _parse_tick(raw: dict[str, Any]) -> Quote | None:
        """Parse a raw KiteTicker tick into a ``Quote`` domain entity.

        Args:
            raw: A raw tick dictionary from KiteTicker.

        Returns:
            A ``Quote`` instance, or ``None`` if the tick could not be parsed.
        """
        instrument_token = raw.get("instrument_token")
        ltp = raw.get("last_price")
        volume = raw.get("volume_traded")
        timestamp = raw.get("timestamp")

        if ltp is None:
            return None

        tick_at: datetime
        if timestamp:
            if isinstance(timestamp, datetime):
                tick_at = timestamp
            else:
                tick_at = datetime.fromisoformat(str(timestamp))
        else:
            tick_at = datetime.now(timezone.utc)

        if tick_at.tzinfo is None:
            tick_at = tick_at.replace(tzinfo=timezone.utc)

        symbol_str = f"token:{instrument_token}" if instrument_token else "unknown"

        return Quote(
            symbol=symbol_str,
            ltp=Decimal(str(ltp)),
            volume=int(volume) if volume else 0,
            tick_at=tick_at,
            bid=Decimal(str(raw.get("bid"))) if raw.get("bid") else None,
            ask=Decimal(str(raw.get("ask"))) if raw.get("ask") else None,
        )
