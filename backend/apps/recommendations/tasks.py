from __future__ import annotations

import logging

from celery import shared_task

logger = logging.getLogger(__name__)


@shared_task(
    name="tradevision.recommendations.compose_explanation",
    queue="ai_reasoning",
    bind=True,
    max_retries=2,
    default_retry_delay=5,
)
def compose_explanation(
    self,
    validated_response: dict,
    confidence_result: dict | None = None,
    strategy_id: str | None = None,
) -> dict:
    from apps.recommendations.services import ExplanationComposer
    from apps.strategy_registry.models import TradingStrategy

    strategy = None
    if strategy_id:
        try:
            strategy = TradingStrategy.objects.get(id=strategy_id)
        except TradingStrategy.DoesNotExist:
            logger.warning(
                "strategy_not_found_for_explanation",
                extra={"strategy_id": strategy_id},
            )

    composer = ExplanationComposer()
    try:
        explanation = composer.compose(
            validated_response=validated_response,
            confidence_result=confidence_result,
            strategy=strategy,
        )
    except Exception:
        logger.exception("explanation_composition_failed, using fallback")
        explanation = composer.compose_fallback(
            validated_response=validated_response,
        )

    return {
        "recommendation_id": str(explanation.recommendation_id),
        "composed_explanation": explanation.composed_explanation,
    }
