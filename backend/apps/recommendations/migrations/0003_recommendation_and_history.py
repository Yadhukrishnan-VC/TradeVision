import uuid

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("rule_engine", "0001_initial"),
        ("recommendations", "0002_alter_recommendationexplanation_created_at_and_more"),
    ]

    operations = [
        migrations.CreateModel(
            name="Recommendation",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("created_at", models.DateTimeField(auto_now_add=True, db_index=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("is_deleted", models.BooleanField(db_index=True, default=False)),
                ("deleted_at", models.DateTimeField(blank=True, null=True)),
                ("symbol", models.CharField(db_index=True, max_length=50)),
                ("analysis_event_id", models.UUIDField(blank=True, null=True, unique=True)),
                ("strategy_id", models.UUIDField(blank=True, null=True)),
                ("confidence_evaluation_id", models.UUIDField(blank=True, null=True)),
                ("direction", models.CharField(db_index=True, max_length=20)),
                ("confidence_score", models.DecimalField(decimal_places=2, max_digits=5)),
                ("status", models.CharField(choices=[("DRAFT", "Draft"), ("PUBLISHED", "Published"), ("ACCEPTED", "Accepted"), ("REJECTED", "Rejected"), ("EXPIRED", "Expired")], db_index=True, default="DRAFT", max_length=20)),
                ("published_at", models.DateTimeField(blank=True, null=True)),
                ("rule_execution", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="recommendations", to="rule_engine.ruleexecution")),
            ],
            options={
                "verbose_name": "Recommendation",
                "verbose_name_plural": "Recommendations",
                "db_table": "recommendations_recommendation",
            },
        ),
        migrations.AddIndex(
            model_name="recommendation",
            index=models.Index(fields=["symbol", "status"], name="recommendat_symbol_ea83d2_idx"),
        ),
        migrations.CreateModel(
            name="RecommendationStatusHistory",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("created_at", models.DateTimeField(auto_now_add=True, db_index=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("is_deleted", models.BooleanField(db_index=True, default=False)),
                ("deleted_at", models.DateTimeField(blank=True, null=True)),
                ("from_status", models.CharField(max_length=20)),
                ("to_status", models.CharField(max_length=20)),
                ("reason", models.TextField(blank=True, default="")),
                ("changed_by", models.CharField(default="system", max_length=255)),
                ("recommendation", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="status_history", to="recommendations.recommendation")),
            ],
            options={
                "verbose_name": "Recommendation Status History",
                "verbose_name_plural": "Recommendation Status Histories",
                "db_table": "recommendations_status_history",
                "ordering": ["-created_at"],
            },
        ),
    ]
