from __future__ import annotations

from django.db import models

from core.models import BaseModel


class MemoryEntry(BaseModel):
    recommendation_id = models.CharField(max_length=255, db_index=True)
    event_type = models.CharField(max_length=255, db_index=True)
    payload = models.JSONField(default=dict)
    occurred_at = models.DateTimeField(db_index=True)

    class Meta:
        db_table = "trader_memory_memoryentry"
        verbose_name = "Memory Entry"
        verbose_name_plural = "Memory Entries"
        constraints = [
            models.UniqueConstraint(
                fields=["recommendation_id", "event_type", "occurred_at"],
                name="uq_memory_entry_unique",
            ),
        ]
        indexes = [
            models.Index(fields=["recommendation_id", "event_type"]),
        ]

    def __str__(self) -> str:
        return f"MemoryEntry({self.recommendation_id}/{self.event_type})"


class MemoryProjection(BaseModel):
    strategy_id = models.CharField(max_length=255, unique=True, db_index=True)
    sample_size = models.IntegerField(default=0)
    win_rate = models.DecimalField(max_digits=8, decimal_places=6, default=0)
    avg_confidence_at_publish = models.DecimalField(max_digits=5, decimal_places=2, default=0)
    last_recomputed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "trader_memory_memoryprojection"
        verbose_name = "Memory Projection"
        verbose_name_plural = "Memory Projections"

    def __str__(self) -> str:
        return f"MemoryProjection(strategy={self.strategy_id})"
