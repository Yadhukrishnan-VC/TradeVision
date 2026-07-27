import uuid

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("strategy_registry", "0001_initial"),
    ]

    operations = [
        migrations.CreateModel(
            name="PromptVersion",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("created_at", models.DateTimeField(auto_now_add=True, db_index=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("is_deleted", models.BooleanField(db_index=True, default=False)),
                ("deleted_at", models.DateTimeField(blank=True, null=True)),
                ("event_type", models.CharField(db_index=True, max_length=64)),
                ("version_hash", models.CharField(db_index=True, max_length=64)),
                ("source_snapshot", models.TextField()),
                ("is_active", models.BooleanField(db_index=True, default=False)),
                ("activated_at", models.DateTimeField(blank=True, null=True)),
                (
                    "activated_by",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="prompt_versions_activated",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={
                "ordering": ["-created_at"],
                "indexes": [
                    models.Index(fields=["event_type", "is_active"], name="ai_engine_p_event_t_e5d79b_idx"),
                ],
                "unique_together": {("event_type", "version_hash")},
            },
        ),
        migrations.CreateModel(
            name="ConfidenceEvaluation",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("created_at", models.DateTimeField(auto_now_add=True, db_index=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("is_deleted", models.BooleanField(db_index=True, default=False)),
                ("deleted_at", models.DateTimeField(blank=True, null=True)),
                ("packet_id", models.UUIDField(db_index=True)),
                ("raw_confidence", models.FloatField()),
                ("adjusted_confidence", models.FloatField()),
                ("threshold_met", models.BooleanField(default=False)),
                ("adjustment_reasons", models.JSONField(default=list)),
                (
                    "strategy",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="confidence_evaluations",
                        to="strategy_registry.tradingstrategy",
                    ),
                ),
            ],
            options={
                "verbose_name": "Confidence Evaluation",
                "verbose_name_plural": "Confidence Evaluations",
                "ordering": ["-created_at"],
            },
        ),
    ]
