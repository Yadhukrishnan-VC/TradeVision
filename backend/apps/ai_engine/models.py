from __future__ import annotations

from django.conf import settings
from django.db import models

from core.models import BaseModel


class PromptVersion(BaseModel):
    event_type = models.CharField(max_length=64, db_index=True)
    version_hash = models.CharField(max_length=64, db_index=True)
    source_snapshot = models.TextField()
    is_active = models.BooleanField(default=False, db_index=True)
    activated_at = models.DateTimeField(null=True, blank=True)
    activated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="prompt_versions_activated",
    )

    class Meta:
        ordering = ["-created_at"]
        unique_together = ("event_type", "version_hash")
        indexes = [
            models.Index(fields=["event_type", "is_active"]),
        ]

    def __str__(self) -> str:
        return f"PromptVersion({self.event_type}, {self.version_hash[:12]}, active={self.is_active})"


class ConfidenceEvaluation(BaseModel):
    packet_id = models.UUIDField(db_index=True)
    raw_confidence = models.FloatField()
    adjusted_confidence = models.FloatField()
    threshold_met = models.BooleanField(default=False)
    adjustment_reasons = models.JSONField(default=list)
    strategy = models.ForeignKey(
        "strategy_registry.TradingStrategy",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="confidence_evaluations",
    )

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "Confidence Evaluation"
        verbose_name_plural = "Confidence Evaluations"

    def __str__(self) -> str:
        return f"ConfidenceEvaluation(packet={self.packet_id}, raw={self.raw_confidence}, adj={self.adjusted_confidence})"
