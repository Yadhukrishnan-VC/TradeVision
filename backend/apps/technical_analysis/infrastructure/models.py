from __future__ import annotations

import uuid

from django.db import models

from apps.common.infrastructure.model_mixins import TimestampedModel


class TASnapshot(TimestampedModel):
    """Persistent storage for TradingView technical analysis snapshots.

    Each row captures a single snapshot of indicator values computed by
    a TradingView Pine Script at a point in time.  The raw payload is
    preserved verbatim and the Pine Script metadata (pine_id,
    pine_version, etc.) is extracted into dedicated columns for
    queryability.

    Indexes:
        - ``symbol``: Filtering by symbol.
        - ``snapshot_timestamp``: Time-based range queries.
        - ``(symbol, snapshot_timestamp)``: Most common access pattern.
        - ``pine_id``: Finding snapshots produced by a specific script.
    """

    id = models.UUIDField(
        primary_key=True,
        default=uuid.uuid4,
        editable=False,
        help_text="Unique identifier for this technical analysis snapshot.",
    )
    symbol = models.CharField(
        max_length=100,
        db_index=True,
        help_text="Trading symbol (e.g. RELIANCE, AAPL).",
    )
    exchange = models.CharField(
        max_length=50,
        blank=True,
        default="",
        help_text="Exchange code (e.g. NSE, BSE, NASDAQ).",
    )
    timeframe = models.CharField(
        max_length=20,
        blank=True,
        default="",
        help_text="Chart timeframe (e.g. 15min, 1D).",
    )
    pine_id = models.CharField(
        max_length=255,
        blank=True,
        default="",
        db_index=True,
        help_text="Pine Script identifier from TradingView.",
    )
    pine_version = models.CharField(
        max_length=50,
        blank=True,
        default="",
        help_text="Pine Script version string.",
    )
    pine_timestamp = models.BigIntegerField(
        null=True,
        blank=True,
        help_text="Pine Script bar time (UNIX milliseconds).",
    )
    indicators = models.JSONField(
        default=dict,
        blank=True,
        help_text="Normalised indicator values keyed by indicator name.",
    )
    raw_payload = models.JSONField(
        default=dict,
        blank=True,
        help_text="Complete raw webhook payload preserved verbatim.",
    )
    snapshot_timestamp = models.DateTimeField(
        db_index=True,
        help_text="UTC datetime of the snapshot (from TradingView bar time).",
    )
    received_at = models.DateTimeField(
        auto_now_add=True,
        help_text="UTC datetime when this snapshot was received.",
    )

    class Meta:
        app_label = "technical_analysis"
        db_table = "technical_analysis_snapshot"
        verbose_name = "Technical Analysis Snapshot"
        verbose_name_plural = "Technical Analysis Snapshots"
        indexes = [
            models.Index(
                fields=["symbol", "snapshot_timestamp"],
                name="idx_ta_symbol_timestamp",
            ),
            models.Index(
                fields=["pine_id", "snapshot_timestamp"],
                name="idx_ta_pine_timestamp",
            ),
        ]
        ordering = ["-snapshot_timestamp"]

    def __str__(self) -> str:
        return f"TASnapshot({self.symbol}, {self.snapshot_timestamp})"
