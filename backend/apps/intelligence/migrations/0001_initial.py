import uuid

from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True

    dependencies = []

    operations = [
        migrations.CreateModel(
            name="PineOutput",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("symbol", models.CharField(db_index=True, max_length=20)),
                ("timeframe", models.CharField(help_text="e.g. 1D, 4h, 1h, 15m", max_length=10)),
                ("indicator_name", models.CharField(help_text="e.g. super_trend, rsi_macd", max_length=50)),
                ("values", models.JSONField(help_text="Indicator values as key-value pairs")),
                ("detected_timestamp", models.DateTimeField(help_text="When the indicator was calculated")),
                ("ingested_at", models.DateTimeField(auto_now_add=True)),
                ("source", models.CharField(default="pine_script", max_length=50)),
            ],
            options={
                "verbose_name": "Pine Script Output",
                "verbose_name_plural": "Pine Script Outputs",
                "db_table": "intelligence_pineoutput",
                "unique_together": {("symbol", "timeframe", "indicator_name")},
                "indexes": [
                    models.Index(fields=["symbol", "-detected_timestamp"], name="intelligen_symbol_0e1afc_idx"),
                    models.Index(fields=["timeframe", "indicator_name"], name="intelligen_timefra_90f52b_idx"),
                ],
            },
        ),
    ]
