from __future__ import annotations

import uuid

from django.db import migrations, models


class Migration(migrations.Migration):
    initial = True

    dependencies: list[tuple[str, str]] = []

    operations = [
        migrations.CreateModel(
            name="AuditLogEntry",
            fields=[
                ("created_at", models.DateTimeField(auto_now_add=True, db_index=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("actor", models.CharField(choices=[("system", "System"), ("user", "User"), ("ai", "AI")], max_length=16)),
                ("action", models.CharField(max_length=255)),
                ("target_type", models.CharField(max_length=255)),
                ("target_id", models.CharField(max_length=255)),
                ("metadata", models.JSONField()),
                ("occurred_at", models.DateTimeField(db_index=True)),
            ],
            options={
                "db_table": "audit_log_auditlogentry",
                "verbose_name": "Audit Log Entry",
                "verbose_name_plural": "Audit Log Entries",
            },
        ),
        migrations.AddIndex(
            model_name="auditlogentry",
            index=models.Index(fields=["target_type", "target_id"], name="audit_log_a_target__d5ccad_idx"),
        ),
        migrations.AddIndex(
            model_name="auditlogentry",
            index=models.Index(fields=["occurred_at"], name="audit_log_a_occurre_070e7a_idx"),
        ),
    ]
