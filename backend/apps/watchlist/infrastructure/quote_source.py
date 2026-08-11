from __future__ import annotations

import logging
from decimal import Decimal

from apps.common.domain.value_objects import Symbol

logger = logging.getLogger(__name__)


class MarketDataQuoteLookup:
    """Adapters ``MarketDataService.get_quote`` to the quote-lookup port.

    This is the only market-data dependency in the watchlist app (WATCH-1
    section O). Quote enrichment is strictly best-effort: an unavailable
    quote degrades to ``None`` and is logged at DEBUG — never WARNING/ERROR —
    because a missing price is expected, benign state for a watchlist.
    """

    implementation_name = "market_data_v1"

    def get_latest_price(self, symbol: Symbol) -> Decimal | None:
        try:
            from apps.market_data.application.market_data_service import (
                get_market_data_service,
            )

            quote = get_market_data_service().get_quote(symbol)
            return quote.ltp
        except Exception as exc:  # noqa: BLE001 — fail-open port
            logger.debug(
                "watchlist_quote_lookup_failed",
                extra={
                    "symbol": symbol.as_broker_string(),
                    "source": self.implementation_name,
                    "error": str(exc),
                },
            )
            return None
