"""
TradeVision AI — Abstract market data provider interface and data contracts.

Defines the contract that all market data providers must implement.
Each provider exposes the same lifecycle (validate_connection, health_check,
fetch, close) regardless of the underlying data vendor.

Frozen dataclasses enforce immutability for all data transfer objects.
All datetime fields are validated as timezone-aware in ``__post_init__``.
"""

import logging
import uuid
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from typing import Any, ClassVar

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Request and response dataclasses
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class MarketDataRequest:
    """
    A request for OHLCV market data for a specific symbol and time range.

    Attributes:
        symbol:         NSE/BSE stock symbol (e.g. ``"RELIANCE"``).
        interval:       Bar interval string: ``"1min"``, ``"5min"``,
                        ``"15min"``, ``"1hr"``, ``"1D"``.
        from_timestamp: Start of the requested range (UTC, timezone-aware).
        to_timestamp:   End of the requested range (UTC, timezone-aware).
        request_id:     Optional caller-provided ID for correlation.
    """

    symbol: str
    interval: str
    from_timestamp: datetime
    to_timestamp: datetime
    request_id: str = ""

    def __post_init__(self) -> None:
        if self.from_timestamp.tzinfo is None:
            raise ValueError(
                "MarketDataRequest.from_timestamp must be timezone-aware."
            )
        if self.to_timestamp.tzinfo is None:
            raise ValueError(
                "MarketDataRequest.to_timestamp must be timezone-aware."
            )
        if self.from_timestamp >= self.to_timestamp:
            raise ValueError(
                "from_timestamp must be strictly before to_timestamp. "
                f"Got: from={self.from_timestamp!r}, to={self.to_timestamp!r}"
            )
        if not self.symbol:
            raise ValueError("MarketDataRequest.symbol must not be empty.")


@dataclass(frozen=True)
class OHLCVBar:
    """
    A single OHLCV (Open / High / Low / Close / Volume) price bar.

    All price fields use ``Decimal`` to preserve precision across
    aggregation and indicator computation.

    Attributes:
        timestamp:    Bar open time (UTC, timezone-aware).
        open_price:   Opening price for the bar interval.
        high:         Highest traded price within the interval.
        low:          Lowest traded price within the interval.
        close_price:  Closing price for the bar interval.
        volume:       Total number of shares traded in the interval.
    """

    timestamp: datetime
    open_price: Decimal
    high: Decimal
    low: Decimal
    close_price: Decimal
    volume: int

    def __post_init__(self) -> None:
        if self.timestamp.tzinfo is None:
            raise ValueError(
                "OHLCVBar.timestamp must be timezone-aware. "
                f"Got naive datetime: {self.timestamp!r}"
            )
        if self.high < self.low:
            raise ValueError(
                f"OHLCVBar.high ({self.high}) must be >= low ({self.low})."
            )
        if self.volume < 0:
            raise ValueError(f"OHLCVBar.volume must be non-negative, got {self.volume}.")


@dataclass(frozen=True)
class MarketDataResponse:
    """
    The response to a ``MarketDataRequest``, containing OHLCV bars.

    Attributes:
        request_id:  Echoes the ``MarketDataRequest.request_id`` for correlation.
        symbol:      The requested stock symbol.
        interval:    The bar interval (e.g. ``"1min"``).
        bars:        Immutable tuple of ``OHLCVBar`` instances, chronological.
        provider:    Provider name that produced this response.
        fetched_at:  UTC datetime when this response was produced.
        is_complete: ``False`` if the provider returned a partial response
                     (e.g. data gap in the requested range).
        meta:        Optional provider-specific metadata.
                     Note: the dict reference is immutable; treat as read-only.
    """

    request_id: str
    symbol: str
    interval: str
    bars: tuple[OHLCVBar, ...]
    provider: str
    fetched_at: datetime
    is_complete: bool = True
    meta: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.fetched_at.tzinfo is None:
            raise ValueError(
                "MarketDataResponse.fetched_at must be timezone-aware. "
                f"Got naive datetime: {self.fetched_at!r}"
            )

    @property
    def bar_count(self) -> int:
        """Return the number of OHLCV bars in this response."""
        return len(self.bars)


# ---------------------------------------------------------------------------
# Abstract provider interface
# ---------------------------------------------------------------------------


class BaseMarketDataProvider(ABC):
    """
    Abstract interface for all market data providers.

    Every concrete provider (Mock, NSE vendor, broker API) must implement
    the full lifecycle contract defined here. The factory returns a
    ``BaseMarketDataProvider`` instance — application code never imports
    concrete provider classes.

    Lifecycle::

        provider = MarketDataProviderFactory.get_provider()
        ok = provider.validate_connection()
        status = provider.health_check()
        response = provider.fetch(request)
        provider.close()

    Class attributes:
        provider_name: Unique string identifier matching ``settings.MARKET_DATA_PROVIDER``.
    """

    provider_name: ClassVar[str]

    @abstractmethod
    def validate_connection(self) -> bool:
        """
        Verify that the provider is reachable and credentials are valid.

        Returns:
            ``True`` if the connection is healthy.

        Raises:
            DataProviderError: If the connection cannot be established.
        """

    @abstractmethod
    def health_check(self) -> dict[str, Any]:
        """
        Return a health status dictionary for this provider.

        The returned dict must include at minimum:
            - ``status``:     ``"healthy"`` | ``"degraded"`` | ``"unhealthy"``
            - ``provider``:   ``self.provider_name``
            - ``latency_ms``: float

        Returns:
            Status dictionary for inclusion in a ``HealthResponse``.
        """

    @abstractmethod
    def fetch(self, request: MarketDataRequest) -> MarketDataResponse:
        """
        Retrieve OHLCV bars for the symbol and time range in ``request``.

        Args:
            request: A populated ``MarketDataRequest``.

        Returns:
            ``MarketDataResponse`` containing chronological OHLCV bars.

        Raises:
            DataIngestionError:  If the provider returns an error response.
            DataProviderError:   On connection or authentication failures.
        """

    @abstractmethod
    def close(self) -> None:
        """
        Release all resources held by this provider.

        Called by ``MarketDataProviderFactory.reset()`` and at shutdown.
        """

    def __repr__(self) -> str:
        """Return an unambiguous developer representation."""
        return f"<{self.__class__.__name__} provider={self.provider_name!r}>"
