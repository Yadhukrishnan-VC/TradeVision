from __future__ import annotations

import uuid

import django.db.models.functions.datetime
from django.db import migrations, models


class Migration(migrations.Migration):
    initial = True

    dependencies: list[tuple[str, str]] = []

    operations = [
        migrations.CreateModel(
            name="Signal",
            fields=[
                (
                    "id",
                    models.UUIDField(
                        default=uuid.uuid4,
                        editable=False,
                        primary_key=True,
                        serialize=False,
                    ),
                ),
                (
                    "account_id",
                    models.UUIDField(blank=True, db_index=True, null=True),
                ),
                (
                    "instrument_symbol",
                    models.CharField(db_index=True, max_length=50),
                ),
                ("timeframe", models.CharField(max_length=10)),
                (
                    "direction",
                    models.CharField(
                        choices=[("BUY", "BUY"), ("SELL", "SELL"), ("WAIT", "WAIT")],
                        max_length=4,
                    ),
                ),
                ("confidence_hint", models.FloatField(default=0.0)),
                (
                    "indicator_snapshot",
                    models.JSONField(blank=True, default=dict),
                ),
                (
                    "source_alert_id",
                    models.CharField(db_index=True, max_length=255),
                ),
                (
                    "created_at",
                    models.DateTimeField(
                        auto_now_add=True,
                        db_index=True,
                    ),
                ),
            ],
            options={
                "db_table": "signals_engine_signal",
                "verbose_name": "Signal",
                "verbose_name_plural": "Signals",
                "indexes": [
                    models.Index(
                        fields=["instrument_symbol", "created_at"],
                        name="signals_engine_signal_sym_created",
                    ),
                    models.Index(
                        fields=["source_alert_id", "created_at"],
                        name="signals_engine_signal_src_created",
                    ),
                ],
            },
        ),
    ]
