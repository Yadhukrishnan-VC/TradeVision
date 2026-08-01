from __future__ import annotations

import logging
from decimal import Decimal

logger = logging.getLogger(__name__)

_CREATED_EVENT = "recommendations.RecommendationCreated"
_STATUS_EVENT = "recommendations.RecommendationStatusChanged"


def get_historical_recommendation_accuracy(symbol: str) -> Decimal | None:
    """Return the historical win rate of recommendations for ``symbol``.

    Read-only enrichment from Trader Memory (ADR-007 §5.6, gated by
    ``PATTERN_ENGINE_ACCURACY_LOOKUP_ENABLED`` at the call site):

    - ``RecommendationCreated`` events carry ``payload["symbol"]`` and give
      us the set of recommendation IDs for the symbol.
    - ``RecommendationStatusChanged`` events carry ``payload["to_status"]``
      (ACCEPTED/REJECTED) keyed by ``recommendation_id``.

    Win rate = ``accepted / (accepted + rejected)``; returns ``None`` when no
    resolution events exist for the symbol. Never raises — any failure
    degrades to ``None`` so pattern analysis is never blocked by enrichment.
    """
    try:
        from apps.trader_memory.infrastructure.models import MemoryEntry

        created = MemoryEntry.objects.filter(
            event_type=_CREATED_EVENT,
            payload__symbol__iexact=symbol,
        ).values_list("recommendation_id", flat=True)
        ids = [rid for rid in created if rid]
        if not ids:
            return None

        statuses = MemoryEntry.objects.filter(
            event_type=_STATUS_EVENT,
            recommendation_id__in=ids,
            payload__to_status__in=["ACCEPTED", "REJECTED"],
        ).values_list("payload__to_status", flat=True)

        accepted = sum(1 for s in statuses if s == "ACCEPTED")
        total = len(statuses)
        if total == 0:
            return None

        return Decimal(str(accepted / total))
    except Exception:
        logger.exception(
            "pe_accuracy_lookup_failed",
            extra={"symbol": symbol},
        )
        return None


__all__ = ["get_historical_recommendation_accuracy"]
