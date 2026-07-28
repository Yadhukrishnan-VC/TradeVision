from __future__ import annotations

import logging
import uuid
from decimal import Decimal

from celery import shared_task

from core.tasks.base import BaseTask, AI_MAX_RETRIES, AI_RETRY_DELAY
from apps.recommendations.tasks import compose_explanation

logger = logging.getLogger(__name__)


@shared_task(
    name="tradevision.recommendations.create_recommendation",
    queue="ai_reasoning",
    bind=True,
    base=BaseTask,
    max_retries=AI_MAX_RETRIES,
    default_retry_delay=AI_RETRY_DELAY,
)
def create_recommendation(
    self,
    symbol: str,
    rule_id: str,
    analysis_event_id: str | None = None,
    trigger_data: dict | None = None,
    correlation_id: str = "",
) -> dict:
    from apps.recommendations.application.recommendation_command_service import RecommendationCommandService

    direction = _derive_direction(trigger_data or {})
    confidence_score = _derive_confidence(trigger_data or {})

    service = RecommendationCommandService()
    aggregate = service.create_from_ai_response(
        symbol=symbol,
        direction=direction,
        confidence_score=confidence_score,
        analysis_event_id=uuid.UUID(analysis_event_id) if analysis_event_id else None,
    )

    validated_response = {
        "recommendation_id": str(aggregate.id),
        "trade_explanation": f"Rule {rule_id} triggered for {symbol}",
        "risk_explanation": "Standard risk assessment required",
    }

    compose_explanation.delay(
        validated_response=validated_response,
        confidence_result=None,
        strategy_id=None,
    )

    return {
        "recommendation_id": str(aggregate.id),
        "symbol": symbol,
        "direction": direction,
        "status": aggregate.status,
    }


def _derive_direction(trigger_data: dict) -> str:
    from core.ai.signals import IntelligenceSignal, map_signal_to_recommendation
    from core.constants import RecommendationDirection

    change_pct_str = trigger_data.get("change_pct", "0")
    try:
        change_pct = float(change_pct_str)
    except (ValueError, TypeError):
        change_pct = 0.0

    if change_pct > 0:
        signal = IntelligenceSignal.BUY
    elif change_pct < 0:
        signal = IntelligenceSignal.SELL
    else:
        signal = IntelligenceSignal.WAIT

    return map_signal_to_recommendation(signal)


def _derive_confidence(trigger_data: dict) -> Decimal:
    return Decimal("0.70")
