from __future__ import annotations

import logging
import math
import time
from datetime import datetime, timedelta
from decimal import Decimal
from random import Random
from typing import Any, ClassVar

from core.exceptions import DataProviderError
from core.market_data.base_provider import (
    BaseMarketDataProvider,
    MarketDataRequest,
    MarketDataResponse,
    OHLCVBar,
)
from core.utils import get_now, to_utc

logger = logging.getLogger(__name__)

_PAPER_BAR_COUNT: int = 20
_PAPER_TICK_SIZE: Decimal = Decimal("0.05")


class PaperMarketDataProvider(BaseMarketDataProvider):
    """Paper / simulated market data provider for development and testing.

    Generates synthetic OHLCV data using a seeded pseudo-random walk so
    results are deterministic for the same symbol and timestamp. Unlike
    ``MockMarketDataProvider``, this provider simulates more realistic
    intraday volatility and supports any interval.

    Use this provider when you need realistic-looking data without an
    external API connection. Switch to ``zerodha`` for production.
    """

    provider_name: ClassVar[str] = "paper"

    def validate_connection(self) -> bool:
        """Always returns ``True`` — the paper provider is self-contained."""
        return True

    def health_check(self) -> dict[str, Any]:
        """Return a healthy status with zero latency."""
        return {
            "status": "healthy",
            "provider": self.provider_name,
            "latency_ms": 0.0,
            "note": "Paper provider — simulated data.",
        }

    def fetch(self, request: MarketDataRequest) -> MarketDataResponse:
        """Return synthetic OHLCV bars for the requested symbol and range.

        Prices are generated using a seeded deterministic random walk so
        the same symbol and time range always produce identical results.

        Args:
            request: A populated ``MarketDataRequest``.

        Returns:
            ``MarketDataResponse`` with synthetic ``OHLCVBar`` instances.
        """
        start = time.monotonic()
        bars = self._generate_bars(request)
        latency_ms = round((time.monotonic() - start) * 1000, 2)

        return MarketDataResponse(
            request_id=request.request_id or "",
            symbol=request.symbol,
            interval=request.interval,
            bars=tuple(bars),
            provider=self.provider_name,
            fetched_at=get_now(),
            is_complete=True,
            meta={"paper": True, "bar_count": len(bars)},
        )

    def fetch_instruments(self) -> list[dict[str, Any]]:
        """Return a minimal set of synthetic instruments for paper trading.

        This enables ``InstrumentSyncService`` to work with the paper
        provider without any external API.
        """
        symbols = [
            ("NSE", "RELIANCE", "Reliance Industries Ltd", "EQ"),
            ("NSE", "TCS", "Tata Consultancy Services Ltd", "EQ"),
            ("NSE", "INFY", "Infosys Ltd", "EQ"),
            ("NSE", "HDFCBANK", "HDFC Bank Ltd", "EQ"),
            ("NSE", "ICICIBANK", "ICICI Bank Ltd", "EQ"),
            ("NSE", "SBIN", "State Bank of India", "EQ"),
            ("NSE", "BHARTIARTL", "Bharti Airtel Ltd", "EQ"),
            ("NSE", "ITC", "ITC Ltd", "EQ"),
            ("NSE", "WIPRO", "Wipro Ltd", "EQ"),
            ("NSE", "TATAMOTORS", "Tata Motors Ltd", "EQ"),
        ]
        return [
            {
                "instrument_token": 1000 + idx,
                "exchange": exc,
                "tradingsymbol": sym,
                "name": name,
                "segment": "EQUITY",
                "lot_size": 1,
                "tick_size": Decimal("0.05"),
                "instrument_type": typ,
                "expiry": None,
                "is_active": True,
            }
            for idx, (exc, sym, name, typ) in enumerate(symbols)
        ]

    def close(self) -> None:
        """No resources to release for the paper provider."""
        logger.debug("paper_provider_closed")

    def _generate_bars(self, request: MarketDataRequest) -> list[OHLCVBar]:
        """Generate deterministic OHLCV bars using a seeded random walk."""
        seed = abs(hash(f"{request.symbol}:{request.interval}")) % (2**31)
        rng = Random(seed)

        base_price = Decimal(500 + (seed % 5000))
        bars: list[OHLCVBar] = []

        duration = (request.to_timestamp - request.from_timestamp).total_seconds()
        bar_minutes = self._estimate_bar_minutes(request.interval)
        bar_count = max(1, min(_PAPER_BAR_COUNT, int(duration / 60 / max(1, bar_minutes))))

        current_price = base_price
        for i in range(bar_count):
            change_pct = Decimal(str(rng.gauss(0, 0.005))).quantize(Decimal("0.0001"))
            open_p = current_price.quantize(_PAPER_TICK_SIZE)
            high_p = (open_p * (Decimal("1") + abs(change_pct) * Decimal("2"))).quantize(_PAPER_TICK_SIZE)
            low_p = (open_p * (Decimal("1") - abs(change_pct) * Decimal("2"))).quantize(_PAPER_TICK_SIZE)
            close_p = (open_p * (Decimal("1") + change_pct)).quantize(_PAPER_TICK_SIZE)
            volume = rng.randint(1000, 500000)

            if high_p < low_p:
                high_p, low_p = low_p, high_p

            bar_timestamp = request.from_timestamp + timedelta(minutes=i * bar_minutes)
            bars.append(OHLCVBar(
                timestamp=bar_timestamp,
                open_price=open_p,
                high=high_p,
                low=low_p,
                close_price=close_p,
                volume=volume,
            ))

            current_price = close_p

        return bars

    @staticmethod
    def _estimate_bar_minutes(interval: str) -> int:
        """Map an interval string to the number of minutes per bar."""
        mapping = {
            "1min": 1,
            "3min": 3,
            "5min": 5,
            "10min": 10,
            "15min": 15,
            "30min": 30,
            "1hr": 60,
            "1D": 1440,
            "1W": 10080,
            "1M": 43200,
        }
        return mapping.get(interval, 15)
