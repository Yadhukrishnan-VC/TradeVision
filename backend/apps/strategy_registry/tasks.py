from __future__ import annotations

import logging

from celery import shared_task

from core.events.event_types import EnrichedIntelligencePacket

logger = logging.getLogger(__name__)


@shared_task(
    name="tradevision.strategy_registry.match_packet",
    queue="ai_reasoning",
    bind=True,
    max_retries=2,
    default_retry_delay=5,
)
def match_packet(self, packet_data: dict) -> dict | None:
    from apps.strategy_registry.services import StrategyMatcher

    matcher = StrategyMatcher()
    try:
        packet = _deserialize_packet(packet_data)
    except Exception:
        logger.exception("failed_to_deserialize_intelligence_packet")
        return None

    if packet is None:
        return None

    strategy = matcher.match(packet)
    if strategy is None:
        logger.info(
            "packet_dropped_no_strategy_match",
            extra={"symbol": getattr(packet, "symbol", "unknown")},
        )
        return None

    return {
        "strategy_id": str(strategy.id),
        "strategy_name": strategy.name,
        "preferred_provider": strategy.preferred_provider,
        "confidence_threshold": float(strategy.confidence_threshold),
        "risk_threshold": float(strategy.risk_threshold),
        "packet_data": packet_data,
    }


def _deserialize_packet(data: dict) -> EnrichedIntelligencePacket | None:
    if not data:
        return None
    try:
        packet_dict = data.get("packet", data)
        from core.events.event_types import IntelligencePacket

        intel_packet = IntelligencePacket(**packet_dict)
        enriched = EnrichedIntelligencePacket(packet=intel_packet)
        return enriched
    except Exception:
        logger.exception("packet_deserialization_failed")
        return None
