from __future__ import annotations

import logging
from decimal import Decimal
from typing import Protocol

logger = logging.getLogger(__name__)


class CurrentPriceProvider(Protocol):
    """Broker-independent current-price source for mark-to-market math.

    Portfolio never calls a broker directly (ADR-028 §2.13); the approved
    current-price source is ``MarketDataService.get_quote`` (ADR-028 §2.6,
    §2.7). This small port lets the deterministic portfolio math be tested
    with a fixed price map while production resolves to the real market-data
    service.
    """

    def get_current_price(self, symbol: str) -> Decimal | None:
        """Return the latest price for *symbol*, or ``None`` when unknown."""
        ...


class MarketDataCurrentPriceProvider:
    """Adapters ``MarketDataService.get_quote`` to the price port.

    Follows the repo-wide convention for constructing a ``Symbol`` from a
    plain trading symbol (``core.config.default_exchange`` + uppercase) used
    by ``pattern_engine`` and ``intelligence``. Price lookups are fail-open:
    an unavailable quote yields ``None`` so the caller can fall back to the
    position's average entry price (zero mark-to-market contribution).
    """

    implementation_name = "market_data_v1"

    def get_current_price(self, symbol: str) -> Decimal | None:
        try:
            from apps.common.domain.value_objects import Symbol
            from apps.market_data.application.market_data_service import (
                get_market_data_service,
            )
            from core.config import config

            quote = get_market_data_service().get_quote(
                Symbol(
                    exchange=config.default_exchange,
                    tradingsymbol=symbol.upper(),
                )
            )
            return quote.ltp
        except Exception:
            logger.exception(
                "portfolio_price_lookup_failed",
                extra={"symbol": symbol, "source": self.implementation_name},
            )
            return None
