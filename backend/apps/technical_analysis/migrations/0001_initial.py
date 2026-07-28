from __future__ import annotations

import uuid

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):
    initial = True

    dependencies: list[tuple[str, str]] = []

    operations = [
        migrations.CreateModel(
            name="TASnapshot",
            fields=[
                (
                    "created_at",
                    models.DateTimeField(auto_now_add=True, db_index=True),
                ),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "id",
                    models.UUIDField(
                        default=uuid.uuid4,
                        editable=False,
                        help_text="Unique identifier for this technical analysis snapshot.",
                        primary_key=True,
                        serialize=False,
                    ),
                ),
                (
                    "symbol",
                    models.CharField(
                        db_index=True,
                        help_text="Trading symbol (e.g. RELIANCE, AAPL).",
                        max_length=100,
                    ),
                ),
                (
                    "exchange",
                    models.CharField(
                        blank=True,
                        default="",
                        help_text="Exchange code (e.g. NSE, BSE, NASDAQ).",
                        max_length=50,
                    ),
                ),
                (
                    "timeframe",
                    models.CharField(
                        blank=True,
                        default="",
                        help_text="Chart timeframe (e.g. 15min, 1D).",
                        max_length=20,
                    ),
                ),
                (
                    "pine_id",
                    models.CharField(
                        blank=True,
                        db_index=True,
                        default="",
                        help_text="Pine Script identifier from TradingView.",
                        max_length=255,
                    ),
                ),
                (
                    "pine_version",
                    models.CharField(
                        blank=True,
                        default="",
                        help_text="Pine Script version string.",
                        max_length=50,
                    ),
                ),
                (
                    "pine_timestamp",
                    models.BigIntegerField(
                        blank=True,
                        help_text="Pine Script bar time (UNIX milliseconds).",
                        null=True,
                    ),
                ),
                (
                    "indicators",
                    models.JSONField(
                        blank=True,
                        default=dict,
                        help_text="Normalised indicator values keyed by indicator name.",
                    ),
                ),
                (
                    "raw_payload",
                    models.JSONField(
                        blank=True,
                        default=dict,
                        help_text="Complete raw webhook payload preserved verbatim.",
                    ),
                ),
                (
                    "snapshot_timestamp",
                    models.DateTimeField(
                        db_index=True,
                        help_text="UTC datetime of the snapshot (from TradingView bar time).",
                    ),
                ),
                (
                    "received_at",
                    models.DateTimeField(
                        auto_now_add=True,
                        help_text="UTC datetime when this snapshot was received.",
                    ),
                ),
            ],
            options={
                "verbose_name": "Technical Analysis Snapshot",
                "verbose_name_plural": "Technical Analysis Snapshots",
                "db_table": "technical_analysis_snapshot",
                "ordering": ["-snapshot_timestamp"],
            },
        ),
        migrations.AddIndex(
            model_name="tasnapshot",
            index=models.Index(
                fields=["symbol", "snapshot_timestamp"],
                name="idx_ta_symbol_timestamp",
            ),
        ),
        migrations.AddIndex(
            model_name="tasnapshot",
            index=models.Index(
                fields=["pine_id", "snapshot_timestamp"],
                name="idx_ta_pine_timestamp",
            ),
        ),
    ]
