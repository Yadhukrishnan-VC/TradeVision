from __future__ import annotations

import uuid

from django.db import models


class Signal(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    account_id = models.UUIDField(null=True, blank=True, db_index=True)
    instrument_symbol = models.CharField(max_length=50, db_index=True)
    timeframe = models.CharField(max_length=10)
    direction = models.CharField(
        max_length=4,
        choices=[("BUY", "BUY"), ("SELL", "SELL"), ("WAIT", "WAIT")],
    )
    confidence_hint = models.FloatField(default=0.0)
    indicator_snapshot = models.JSONField(default=dict, blank=True)
    source_alert_id = models.CharField(max_length=255, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        app_label = "signals_engine"
        db_table = "signals_engine_signal"
        verbose_name = "Signal"
        verbose_name_plural = "Signals"
        indexes = [
            models.Index(fields=["instrument_symbol", "created_at"]),
            models.Index(fields=["source_alert_id", "created_at"]),
        ]

    def __str__(self) -> str:
        return f"Signal({self.instrument_symbol}, {self.direction}, {self.created_at})"
