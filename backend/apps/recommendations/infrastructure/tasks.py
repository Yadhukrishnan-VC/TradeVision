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
    direction: str = "WATCH",
    confidence_score: str = "0.70",
    strategy_id: str | None = None,
    confidence_evaluation_id: str | None = None,
    analysis_event_id: str | None = None,
    reason: str = "",
    risk_level: str = "MEDIUM",
    risk_explanation: str = "",
    key_factors: list | None = None,
    time_horizon: str = "SHORT",
    provider: str = "fallback",
    validated_response: dict | None = None,
    correlation_id: str = "",
) -> dict:
    from apps.recommendations.application.recommendation_command_service import RecommendationCommandService

    score = Decimal(str(confidence_score))

    service = RecommendationCommandService()
    aggregate = service.create_from_ai_response(
        symbol=symbol,
        direction=direction,
        confidence_score=score,
        analysis_event_id=uuid.UUID(analysis_event_id) if analysis_event_id else None,
        strategy_id=uuid.UUID(strategy_id) if strategy_id else None,
        confidence_evaluation_id=uuid.UUID(confidence_evaluation_id) if confidence_evaluation_id else None,
    )

    response_payload = validated_response or {
        "recommendation_id": str(aggregate.id),
        "trade_explanation": reason or f"AI recommendation for {symbol}",
        "risk_explanation": risk_explanation or "Standard risk assessment required",
    }
    response_payload["recommendation_id"] = str(aggregate.id)

    compose_explanation.delay(
        validated_response=response_payload,
        confidence_result={
            "raw_confidence": float(score),
            "adjusted_confidence": float(score),
            "threshold_met": True,
            "adjustment_reasons": [],
        },
        strategy_id=strategy_id,
    )

    return {
        "recommendation_id": str(aggregate.id),
        "symbol": symbol,
        "direction": direction,
        "status": aggregate.status,
    }
