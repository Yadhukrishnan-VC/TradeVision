from __future__ import annotations

from django.db import models

from core.models import BaseModel


class RecommendationExplanation(BaseModel):
    recommendation_id = models.UUIDField(unique=True, db_index=True)
    trade_explanation = models.TextField()
    risk_explanation = models.TextField()
    confidence_evaluation = models.ForeignKey(
        "ai_engine.ConfidenceEvaluation",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="recommendation_explanations",
    )
    strategy = models.ForeignKey(
        "strategy_registry.TradingStrategy",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="recommendation_explanations",
    )
    composed_explanation = models.TextField()

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "Recommendation Explanation"
        verbose_name_plural = "Recommendation Explanations"

    def __str__(self) -> str:
        return f"RecommendationExplanation(recommendation={self.recommendation_id})"
