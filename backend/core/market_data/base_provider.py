"""
TradeVision AI — Abstract market data provider interface.

Defines the ``BaseMarketDataProvider`` ABC and the request/response data
contracts for the market data ingestion layer.

Lifecycle::

    provider = MockMarketDataProvider()
    provider.validate_connection()   # → True
    status = provider.health_check() # → {"status": "healthy", ...}
    response = provider.fetch(request)
    provider.close()
"""

import abc
import dataclasses
from datetime import datetime
from decimal import Decimal
from typing import Any

from core.exceptions import DataProviderError, DataIngestionError


# ---------------------------------------------------------------------------
# Request / Response dataclasses
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class MarketDataRequest:
    """
    A structured request to a market data provider.

    Attributes:
        symbol:    NSE/BSE stock symbol.
        interval:  Data granularity (e.g. "1min", "5min", "1day").
        start:     Start of the time range (optional).
        end:       End of the time range (optional).
        fields:    Specific data fields to request (optional).
    """

    symbol: str
    interval: str = "1day"
    start: datetime | None = None
    end: datetime | None = None
    fields: tuple[str, ...] = ()


@dataclass(frozen=True)
class MarketDataResponse:
    """
    The response from a market data provider fetch.

    Attributes:
        provider:    Provider name that served this response.
        symbol:      The stock symbol.
        interval:    Data granularity.
        data_points: List of data point dicts (each with OHLCV fields).
        latency_ms:  Round-trip time in milliseconds.
        metadata:    Provider-specific metadata.
    """

    provider: str
    symbol: str
    interval: str
    data_points: tuple[dict[str, Any], ...] = ()
    latency_ms: float = 0.0
    metadata: dict[str, Any] = dataclasses.field(default_factory=dict)


# ---------------------------------------------------------------------------
# Abstract base provider
# ---------------------------------------------------------------------------


class BaseMarketDataProvider(abc.ABC):
    """
    Abstract interface for all market data providers.

    Subclasses must implement the four lifecycle methods.

    Class Attributes:
        provider_name:  Unique identifier (e.g. ``"mock"``, ``"yfinance"``).
    """

    provider_name: str

    @abc.abstractmethod
    def validate_connection(self) -> bool:
        """
        Verify that the provider is reachable and accessible.

        Returns:
            True if the connection is valid.

        Raises:
            DataProviderError: If the provider is unreachable.
        """

    @abc.abstractmethod
    def health_check(self) -> dict[str, Any]:
        """
        Return a health status dict for the provider.

        Returns:
            A dict with at minimum ``{"status": "healthy"|"degraded"|"unhealthy"}``
            and optionally ``latency_ms``, ``detail`` keys.
        """

    @abc.abstractmethod
    def fetch(self, request: MarketDataRequest) -> MarketDataResponse:
        """
        Fetch market data for the given request.

        Args:
            request: The structured market data request.

        Returns:
            A ``MarketDataResponse`` with the fetched data.

        Raises:
            DataIngestionError: On any data retrieval failure.
        """

    @abc.abstractmethod
    def close(self) -> None:
        """Release any resources held by the provider."""
