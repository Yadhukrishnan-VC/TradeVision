from __future__ import annotations

import logging
from typing import Any

from django.conf import settings
from django.utils import timezone

from apps.recommendations.models import RecommendationExplanation

logger = logging.getLogger(__name__)


class ExplanationComposer:
    def compose(
        self,
        validated_response: dict[str, Any],
        confidence_result: dict[str, Any] | None = None,
        strategy: Any = None,
    ) -> RecommendationExplanation:
        trade_explanation = validated_response.get("trade_explanation", "")
        risk_explanation = validated_response.get("risk_explanation", "")
        recommendation_id = validated_response.get("recommendation_id")

        parts = [trade_explanation, risk_explanation]

        if confidence_result:
            adjustment_reasons = confidence_result.get("adjustment_reasons", [])
            if adjustment_reasons:
                adj_section = "Confidence adjustment: " + "; ".join(adjustment_reasons)
                parts.append(adj_section)

        if strategy:
            strategy_info = (
                f"Strategy: {getattr(strategy, 'name', 'Unknown')} "
                f"(threshold: confidence={getattr(strategy, 'confidence_threshold', 'N/A')}, "
                f"risk={getattr(strategy, 'risk_threshold', 'N/A')})"
            )
            parts.append(strategy_info)

        composed = "\n\n".join(parts)

        explanation = RecommendationExplanation(
            recommendation_id=recommendation_id,
            trade_explanation=trade_explanation,
            risk_explanation=risk_explanation,
            strategy=strategy,
            composed_explanation=composed,
        )
        explanation.full_clean()
        explanation.save()
        logger.info(
            "recommendation_explanation_composed",
            extra={"recommendation_id": str(recommendation_id)},
        )
        return explanation

    def compose_fallback(
        self,
        validated_response: dict[str, Any],
    ) -> RecommendationExplanation:
        trade_explanation = validated_response.get("trade_explanation", "")
        risk_explanation = validated_response.get("risk_explanation", "")
        recommendation_id = validated_response.get("recommendation_id")

        composed = trade_explanation + "\n\n" + risk_explanation

        explanation = RecommendationExplanation(
            recommendation_id=recommendation_id,
            trade_explanation=trade_explanation,
            risk_explanation=risk_explanation,
            composed_explanation=composed,
        )
        explanation.full_clean()
        explanation.save()
        logger.warning(
            "recommendation_explanation_fallback",
            extra={"recommendation_id": str(recommendation_id)},
        )
        return explanation
