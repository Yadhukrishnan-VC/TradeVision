"""
TradeVision AI — Intelligence Engine Models.

PineOutput stores the latest Pine Script indicator values per symbol/timeframe.
The AI Brain never computes its own indicators — it always reads from here.
"""

from __future__ import annotations

import uuid

from django.db import models


class PineOutput(models.Model):
    """Stores the latest Pine Script indicator output for a symbol.

    This is the single source of truth for technical indicator values.
    The Technical Analysis app NEVER computes its own indicators — it
    ingests Pine Script output into this table and validates it.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    symbol = models.CharField(max_length=20, db_index=True)
    timeframe = models.CharField(max_length=10, help_text="e.g. 1D, 4h, 1h, 15m")
    indicator_name = models.CharField(max_length=50, help_text="e.g. super_trend, rsi_macd")
    values = models.JSONField(
        help_text="Indicator values as key-value pairs, e.g. {'rsi_14': 62.5, 'macd': 1.23}"
    )
    detected_timestamp = models.DateTimeField(
        help_text="When the indicator was calculated by Pine Script"
    )
    ingested_at = models.DateTimeField(auto_now_add=True)
    source = models.CharField(max_length=50, default="pine_script")

    class Meta:
        verbose_name = "Pine Script Output"
        verbose_name_plural = "Pine Script Outputs"
        unique_together = ("symbol", "timeframe", "indicator_name")
        indexes = [
            models.Index(fields=["symbol", "-detected_timestamp"]),
            models.Index(fields=["timeframe", "indicator_name"]),
        ]

    def __str__(self) -> str:
        return f"{self.symbol} ({self.timeframe}) — {self.indicator_name}"
