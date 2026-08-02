from __future__ import annotations

import logging
from datetime import datetime

from core.market_calendar import get_market_calendar

logger = logging.getLogger(__name__)


class MarketCalendarStatusGateway:
    """Concrete :class:`MarketStatusGateway` backed by ``core.market_calendar``.

    Freshness is evaluated against ``settings.TICK_FRESHNESS_THRESHOLD_SECONDS``
    (data older than the threshold at fire time is stale).
    """

    def __init__(self) -> None:
        self._calendar = get_market_calendar()
        self._freshness_threshold_seconds = self._read_freshness_threshold()

    @staticmethod
    def _read_freshness_threshold() -> int:
        from django.conf import settings

        return int(
            getattr(settings, "TICK_FRESHNESS_THRESHOLD_SECONDS", 120)
        )

    def is_market_open(self, reference_dt: datetime) -> bool:
        try:
            return self._calendar.is_market_hours(reference_dt)
        except Exception:
            logger.exception(
                "market_status_check_error",
                extra={"reference_dt": str(reference_dt)},
            )
            return False  # fail-closed: treat as closed

    def is_fresh(self, occurred_at: datetime, reference_dt: datetime) -> bool:
        try:
            age = (reference_dt - occurred_at).total_seconds()
            return age <= self._freshness_threshold_seconds
        except Exception:
            logger.exception(
                "freshness_check_error",
                extra={"occurred_at": str(occurred_at), "reference_dt": str(reference_dt)},
            )
            return False  # fail-closed: treat as stale
