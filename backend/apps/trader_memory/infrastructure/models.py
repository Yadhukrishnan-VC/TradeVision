from __future__ import annotations

from django.db import models

from core.models import BaseModel


class CalibrationDriftRecord(BaseModel):
    """Persisted flag when a rule's live paper outcomes drifted away from its
    backtested expected win rate over a rolling window (Risk Sophistication
    batch — calibration-drift monitoring).

    One row per drifted rule per evaluation pass; the audit trail records the
    exact window, the observed vs expected win rates and the test p-value.
    """

    rule_id = models.CharField(max_length=255, db_index=True)
    window_start = models.DateTimeField()
    window_end = models.DateTimeField()
    n_trades = models.IntegerField()
    live_win_rate = models.DecimalField(max_digits=8, decimal_places=6)
    expected_win_rate = models.DecimalField(max_digits=8, decimal_places=6)
    p_value = models.DecimalField(max_digits=10, decimal_places=8)
    drifted = models.BooleanField(default=True)

    class Meta:
        db_table = "trader_memory_calibrationdriftrecord"
        verbose_name = "Calibration Drift Record"
        verbose_name_plural = "Calibration Drift Records"
        indexes = [
            models.Index(fields=["rule_id", "window_start"]),
        ]

    def __str__(self) -> str:
        return f"CalibrationDriftRecord({self.rule_id} @ {self.window_start})"


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
