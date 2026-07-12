"""
TradeVision AI — Mock market data provider.

Fully implements ``BaseMarketDataProvider`` with deterministic placeholder
data. Used for development, testing, and CI pipelines where no external
market data API is available. No network I/O is performed.
"""

import time
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any

from core.market_data.base_provider import (
    BaseMarketDataProvider,
    MarketDataRequest,
    MarketDataResponse,
)


class MockMarketDataProvider(BaseMarketDataProvider):
    """
    Mock market data provider that returns deterministic data.

    Always succeeds — useful for development, integration tests, and
    CI pipelines. No external network calls are made.
    """

    provider_name = "mock"

    def validate_connection(self) -> bool:
        """Mock is always reachable."""
        return True

    def health_check(self) -> dict[str, Any]:
        """Return healthy status immediately."""
        return {
            "status": "healthy",
            "provider": self.provider_name,
            "latency_ms": 0.0,
        }

    def fetch(self, request: MarketDataRequest) -> MarketDataResponse:
        """
        Return deterministic mock data for the requested symbol.

        Generates a single data point with fixed OHLCV values derived
        from the symbol name for reproducibility.
        """
        start = time.monotonic()

        # Deterministic price based on symbol hash
        base_price = Decimal(str(100 + (hash(request.symbol) % 900)))

        data_point = {
            "timestamp": datetime.now(tz=timezone.utc).isoformat(),
            "open": str(base_price),
            "high": str(base_price * Decimal("1.02")),
            "low": str(base_price * Decimal("0.98")),
            "close": str(base_price * Decimal("1.01")),
            "volume": 100000 + (hash(request.symbol) % 900000),
        }

        latency_ms = (time.monotonic() - start) * 1000

        return MarketDataResponse(
            provider=self.provider_name,
            symbol=request.symbol,
            interval=request.interval,
            data_points=(data_point,),
            latency_ms=round(latency_ms, 2),
            metadata={"mock": True},
        )

    def close(self) -> None:
        """No resources to release."""
