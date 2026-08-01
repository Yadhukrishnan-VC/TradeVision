from __future__ import annotations

from django.db import models

from core.models import BaseModel


class Recommendation(BaseModel):
    symbol = models.CharField(max_length=50, db_index=True)
    analysis_event_id = models.UUIDField(null=True, blank=True, unique=True)
    rule_execution = models.ForeignKey(
        "rule_engine.RuleExecution",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="recommendations",
    )
    strategy_id = models.UUIDField(null=True, blank=True)
    confidence_evaluation_id = models.UUIDField(null=True, blank=True)
    provider = models.CharField(max_length=50, default="fallback", db_index=True)
    correlation_id = models.UUIDField(null=True, blank=True)
    direction = models.CharField(max_length=20, db_index=True)
    confidence_score = models.DecimalField(max_digits=5, decimal_places=2)
    status = models.CharField(
        max_length=20,
        choices=[
            ("DRAFT", "Draft"),
            ("PUBLISHED", "Published"),
            ("ACCEPTED", "Accepted"),
            ("REJECTED", "Rejected"),
            ("EXPIRED", "Expired"),
        ],
        default="DRAFT",
        db_index=True,
    )
    published_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "recommendations_recommendation"
        verbose_name = "Recommendation"
        verbose_name_plural = "Recommendations"
        indexes = [
            models.Index(fields=["symbol", "status"]),
        ]

    def __str__(self) -> str:
        return f"Recommendation({self.symbol}/{self.direction}/{self.status})"


class RecommendationStatusHistory(BaseModel):
    recommendation = models.ForeignKey(
        Recommendation,
        on_delete=models.CASCADE,
        related_name="status_history",
    )
    from_status = models.CharField(max_length=20)
    to_status = models.CharField(max_length=20)
    reason = models.TextField(blank=True, default="")
    changed_by = models.CharField(max_length=255, default="system")

    class Meta:
        db_table = "recommendations_status_history"
        verbose_name = "Recommendation Status History"
        verbose_name_plural = "Recommendation Status Histories"
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return f"StatusHistory({self.recommendation_id}: {self.from_status} -> {self.to_status})"
