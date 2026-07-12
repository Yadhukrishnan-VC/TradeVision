"""
TradeVision AI — Mock market data provider.

Fully implements the ``BaseMarketDataProvider`` contract using deterministic
placeholder data. No network requests are made. Suitable for:
    - Phase 0 integration tests
    - CI/CD pipelines without external API access
    - Local development without vendor credentials

Determinism guarantee: given the same ``symbol`` and ``from_timestamp``,
``fetch()`` always returns the same 5 OHLCV bars. The base price is derived
from an MD5 hash of the symbol so different symbols yield different prices.
"""

import hashlib
import logging
import time
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Any, ClassVar

from core.market_data.base_provider import (
    BaseMarketDataProvider,
    MarketDataRequest,
    MarketDataResponse,
    OHLCVBar,
)
from core.utils import get_now

logger = logging.getLogger(__name__)

_MOCK_BAR_COUNT: int = 5
"""Number of OHLCV bars returned per fetch() call."""


class MockMarketDataProvider(BaseMarketDataProvider):
    """
    Deterministic mock market data provider for Phase 0 and testing.

    Returns a fixed set of synthetic OHLCV bars seeded by the requested
    symbol. No external calls are made; all data is computed locally.

    Price seed logic:
        The base price is derived from the first 8 hex digits of the MD5
        hash of the symbol string, clamped to the range [100, 499].
        Each bar adds a small sequential offset to produce realistic-looking
        price movement.
    """

    provider_name: ClassVar[str] = "mock"

    def validate_connection(self) -> bool:
        """
        Always returns ``True`` — the mock provider requires no external connection.

        Returns:
            ``True`` unconditionally.
        """
        logger.debug("mock_provider_validate_connection_called")
        return True

    def health_check(self) -> dict[str, Any]:
        """
        Return a static ``healthy`` status with zero latency.

        Returns:
            Health status dictionary with ``status="healthy"`` and
            ``latency_ms=0.0``.
        """
        return {
            "status": "healthy",
            "provider": self.provider_name,
            "latency_ms": 0.0,
            "note": "Mock provider — no external connection required.",
        }

    def fetch(self, request: MarketDataRequest) -> MarketDataResponse:
        """
        Return deterministic fake OHLCV bars for the requested symbol and range.

        Exactly ``_MOCK_BAR_COUNT`` (5) bars are returned starting at
        ``request.from_timestamp``, with one bar per minute regardless of
        the requested interval. The bars are consistent across calls with
        the same inputs.

        Args:
            request: A populated ``MarketDataRequest``.

        Returns:
            ``MarketDataResponse`` with 5 deterministic ``OHLCVBar`` instances.
        """
        start: float = time.monotonic()
        bars: list[OHLCVBar] = self._generate_bars(request)
        latency_ms: float = round((time.monotonic() - start) * 1000, 2)

        logger.debug(
            "mock_provider_fetch_complete",
            extra={
                "symbol": request.symbol,
                "interval": request.interval,
                "bar_count": len(bars),
                "latency_ms": latency_ms,
            },
        )

        return MarketDataResponse(
            request_id=request.request_id or "",
            symbol=request.symbol,
            interval=request.interval,
            bars=tuple(bars),
            provider=self.provider_name,
            fetched_at=get_now(),
            is_complete=True,
            meta={"mock": True, "bar_count": len(bars)},
        )

    def close(self) -> None:
        """No resources to release for the mock provider."""
        logger.debug(
            "mock_provider_closed",
            extra={"provider": self.provider_name},
        )

    def _generate_bars(self, request: MarketDataRequest) -> list[OHLCVBar]:
        """
        Generate a deterministic list of fake OHLCV bars.

        The base price is seeded by the MD5 hash of the symbol, ensuring
        different symbols produce different price levels while remaining
        fully reproducible.

        Args:
            request: The inbound market data request.

        Returns:
            A list of exactly ``_MOCK_BAR_COUNT`` ``OHLCVBar`` instances.
        """
        symbol_seed: int = int(
            hashlib.md5(request.symbol.encode(), usedforsecurity=False).hexdigest()[:8],
            16,
        )
        base_price: Decimal = Decimal(100 + (symbol_seed % 400))

        bars: list[OHLCVBar] = []
        for i in range(_MOCK_BAR_COUNT):
            offset: Decimal = Decimal(i) * Decimal("0.50")
            open_p: Decimal = (base_price + offset).quantize(Decimal("0.05"))
            high_p: Decimal = (open_p + Decimal("2.00")).quantize(Decimal("0.05"))
            low_p: Decimal = (open_p - Decimal("2.00")).quantize(Decimal("0.05"))
            close_p: Decimal = (open_p + Decimal("0.25")).quantize(Decimal("0.05"))
            volume: int = 10_000 + (i * 500) + (symbol_seed % 5_000)

            bar_timestamp: datetime = request.from_timestamp + timedelta(minutes=i)

            bars.append(
                OHLCVBar(
                    timestamp=bar_timestamp,
                    open_price=open_p,
                    high=high_p,
                    low=low_p,
                    close_price=close_p,
                    volume=volume,
                )
            )

        return bars
