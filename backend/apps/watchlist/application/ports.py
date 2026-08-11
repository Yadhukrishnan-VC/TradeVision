from __future__ import annotations

from decimal import Decimal
from typing import Protocol

from apps.common.domain.value_objects import Symbol


class QuoteLookupPort(Protocol):
    """Best-effort latest-price source for watchlist read enrichment.

    The watchlist read path never depends on a price being available; the
    port returns ``None`` when the market-data source is unavailable so the
    view can degrade to a null price (WATCH-1 section K).
    """

    def get_latest_price(self, symbol: Symbol) -> Decimal | None:
        """Return the latest price for *symbol*, or ``None`` when unknown."""
        ...
