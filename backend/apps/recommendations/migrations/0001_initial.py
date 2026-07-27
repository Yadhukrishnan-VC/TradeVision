import uuid

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        ("ai_engine", "0001_initial"),
        ("strategy_registry", "0001_initial"),
    ]

    operations = [
        migrations.CreateModel(
            name="RecommendationExplanation",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("created_at", models.DateTimeField(auto_now_add=True, db_index=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("is_deleted", models.BooleanField(db_index=True, default=False)),
                ("deleted_at", models.DateTimeField(blank=True, null=True)),
                ("recommendation_id", models.UUIDField(db_index=True, unique=True)),
                ("trade_explanation", models.TextField()),
                ("risk_explanation", models.TextField()),
                ("composed_explanation", models.TextField()),
                (
                    "confidence_evaluation",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="recommendation_explanations",
                        to="ai_engine.confidenceevaluation",
                    ),
                ),
                (
                    "strategy",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="recommendation_explanations",
                        to="strategy_registry.tradingstrategy",
                    ),
                ),
            ],
            options={
                "verbose_name": "Recommendation Explanation",
                "verbose_name_plural": "Recommendation Explanations",
                "ordering": ["-created_at"],
            },
        ),
    ]
