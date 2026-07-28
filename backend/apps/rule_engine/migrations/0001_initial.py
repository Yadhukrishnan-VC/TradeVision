import uuid

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True

    dependencies = []

    operations = [
        migrations.CreateModel(
            name="RuleConfig",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("created_at", models.DateTimeField(auto_now_add=True, db_index=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("is_deleted", models.BooleanField(db_index=True, default=False)),
                ("deleted_at", models.DateTimeField(blank=True, null=True)),
                ("rule_id", models.CharField(db_index=True, max_length=255, unique=True)),
                ("enabled", models.BooleanField(default=True)),
                ("parameters", models.JSONField(blank=True, default=dict)),
                ("severity_override", models.CharField(blank=True, help_text="Override default severity (LOW, MEDIUM, HIGH, CRITICAL)", max_length=20, null=True)),
            ],
            options={
                "verbose_name": "Rule Config",
                "verbose_name_plural": "Rule Configs",
                "db_table": "rule_engine_ruleconfig",
            },
        ),
        migrations.CreateModel(
            name="RuleExecution",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("created_at", models.DateTimeField(auto_now_add=True, db_index=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("is_deleted", models.BooleanField(db_index=True, default=False)),
                ("deleted_at", models.DateTimeField(blank=True, null=True)),
                ("analysis_event_id", models.UUIDField()),
                ("rule_id", models.CharField(db_index=True, max_length=255)),
                ("symbol", models.CharField(db_index=True, max_length=50)),
                ("severity", models.CharField(max_length=20)),
                ("trigger_data", models.JSONField(default=dict)),
                ("published_event_id", models.UUIDField(blank=True, null=True)),
            ],
            options={
                "verbose_name": "Rule Execution",
                "verbose_name_plural": "Rule Executions",
                "db_table": "rule_engine_ruleexecution",
            },
        ),
        migrations.AddConstraint(
            model_name="ruleexecution",
            constraint=models.UniqueConstraint(fields=("analysis_event_id", "rule_id"), name="uq_ruleexecution_event_rule"),
        ),
    ]
