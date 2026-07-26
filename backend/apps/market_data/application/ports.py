from __future__ import annotations

from collections.abc import Callable
from typing import Any, Protocol, runtime_checkable

from apps.market_data.domain.entities import Quote


@runtime_checkable
class TickSource(Protocol):
    """Protocol for real-time tick streaming adapters.

    Unlike ``BaseMarketDataProvider`` which is request-response oriented,
    ``TickSource`` is a streaming interface. It provides a continuous
    flow of ``Quote`` objects as they arrive from the broker/vendor.

    Implementations wrap broker WebSocket connections (e.g. KiteTicker
    for Zerodha) or synthetic generators (e.g. for the ``paper`` provider).
    """

    def subscribe(self, instruments: list[int]) -> None:
        """Subscribe to real-time ticks for the given instrument tokens.

        Args:
            instruments: List of exchange instrument tokens to subscribe to.

        Raises:
            ConnectionError: If the tick source is not connected.
        """
        ...

    def unsubscribe(self, instruments: list[int]) -> None:
        """Unsubscribe from ticks for the given instrument tokens.

        Args:
            instruments: List of exchange instrument tokens to unsubscribe from.
        """
        ...

    def start(self, on_tick: Callable[[Quote], None]) -> None:
        """Start the streaming connection and invoke ``on_tick`` per quote.

        This method is non-blocking; it spawns a background thread or
        returns immediately after setting up the connection. The callback
        is invoked on each incoming tick.

        Args:
            on_tick: Callback invoked with each parsed ``Quote``.
        """
        ...

    def stop(self) -> None:
        """Gracefully stop the streaming connection and release resources."""
        ...

    @property
    def is_connected(self) -> bool:
        """Return ``True`` if the streaming connection is currently active."""
        ...

    @property
    def connection_state(self) -> str:
        """Return a human-readable connection state string.

        Possible values: ``"connected"``, ``"disconnected"``,
        ``"connecting"``, ``"degraded"``.
        """
        ...
