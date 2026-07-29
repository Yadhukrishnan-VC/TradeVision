from __future__ import annotations

import logging
from datetime import datetime
from decimal import Decimal
from typing import Any

from apps.eventbus.domain.events import DomainEvent
from apps.intelligence.infrastructure.market_context_cache import MarketContextCache
from core.events.event_types import PatternContext, PatternMatch

logger = logging.getLogger(__name__)


def _deserialize_pattern_context(payload: dict[str, Any]) -> PatternContext | None:
    try:
        similar_dates_raw = payload.get("similar_dates", [])
        similar_dates = tuple(
            PatternMatch(
                date_str=item["date_str"],
                similarity_score=Decimal(str(item["similarity_score"])),
                outcome_summary=item["outcome_summary"],
            )
            for item in similar_dates_raw
        )
        return PatternContext(
            similar_dates=similar_dates,
            top_analogue_summary=payload.get("top_analogue_summary", ""),
        )
    except (KeyError, ValueError, TypeError) as exc:
        logger.warning("pattern_context_deserialization_failed", extra={"error": str(exc)})
        return None


def handle_pattern_analysis_completed(event: DomainEvent) -> None:
    payload = event.payload
    symbol = payload.get("symbol", "")
    if not symbol:
        logger.warning("pattern_completed_missing_symbol", extra={"event_id": str(event.event_id)})
        return

    pattern_ctx = _deserialize_pattern_context(payload)
    if pattern_ctx is None:
        logger.warning("pattern_completed_malformed_payload", extra={"symbol": symbol})
        return

    cache = MarketContextCache()
    cache.attach_pattern_context(symbol, pattern_ctx)

    logger.info(
        "pattern_context_attached",
        extra={"symbol": symbol, "has_summary": bool(pattern_ctx.top_analogue_summary)},
    )
