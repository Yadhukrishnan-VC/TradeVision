from __future__ import annotations

import uuid

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    initial = True

    dependencies: list[tuple[str, str]] = [
        ("accounts", "0003_seed_default_account"),
    ]

    operations = [
        migrations.CreateModel(
            name="JournalEventLog",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("event_id", models.UUIDField(db_index=True)),
                ("consumer", models.CharField(max_length=255)),
                ("applied_at", models.DateTimeField(auto_now_add=True)),
            ],
            options={
                "db_table": "journal_eventlog",
            },
        ),
        migrations.CreateModel(
            name="JournalEntry",
            fields=[
                ("created_at", models.DateTimeField(auto_now_add=True, db_index=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("correlation_id", models.UUIDField(unique=True)),
                ("signal_snapshot", models.JSONField(blank=True, null=True)),
                ("decision_snapshot", models.JSONField(blank=True, null=True)),
                ("order_events", models.JSONField(default=list)),
                ("position_id", models.UUIDField(blank=True, null=True)),
                ("outcome", models.CharField(blank=True, choices=[("won", "Won"), ("lost", "Lost"), ("breakeven", "Breakeven"), ("no_trade", "No Trade")], max_length=20, null=True)),
                ("realized_pnl", models.DecimalField(blank=True, decimal_places=8, max_digits=20, null=True)),
                ("finalized", models.BooleanField(default=False)),
                ("finalized_at", models.DateTimeField(blank=True, null=True)),
                ("account", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="journal_entries", to="accounts.Account")),
            ],
            options={
                "db_table": "journal_journalentry",
            },
        ),
        migrations.AddConstraint(
            model_name="journaleventlog",
            constraint=models.UniqueConstraint(fields=["event_id", "consumer"], name="uq_journal_eventlog_event_consumer"),
        ),
        migrations.AddIndex(
            model_name="journaleventlog",
            index=models.Index(fields=["event_id", "consumer"], name="journal_even_event_i_d8e7ed_idx"),
        ),
        migrations.AddIndex(
            model_name="journalentry",
            index=models.Index(fields=["account", "finalized"], name="journal_jou_account_3bf73a_idx"),
        ),
    ]
