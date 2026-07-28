import uuid

from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True

    dependencies = []

    operations = [
        migrations.CreateModel(
            name="MemoryEntry",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("created_at", models.DateTimeField(auto_now_add=True, db_index=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("is_deleted", models.BooleanField(db_index=True, default=False)),
                ("deleted_at", models.DateTimeField(blank=True, null=True)),
                ("recommendation_id", models.CharField(db_index=True, max_length=255)),
                ("event_type", models.CharField(db_index=True, max_length=255)),
                ("payload", models.JSONField(default=dict)),
                ("occurred_at", models.DateTimeField(db_index=True)),
            ],
            options={
                "verbose_name": "Memory Entry",
                "verbose_name_plural": "Memory Entries",
                "db_table": "trader_memory_memoryentry",
            },
        ),
        migrations.CreateModel(
            name="MemoryProjection",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("created_at", models.DateTimeField(auto_now_add=True, db_index=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("is_deleted", models.BooleanField(db_index=True, default=False)),
                ("deleted_at", models.DateTimeField(blank=True, null=True)),
                ("strategy_id", models.CharField(db_index=True, max_length=255, unique=True)),
                ("sample_size", models.IntegerField(default=0)),
                ("win_rate", models.DecimalField(decimal_places=6, default=0, max_digits=8)),
                ("avg_confidence_at_publish", models.DecimalField(decimal_places=2, default=0, max_digits=5)),
                ("last_recomputed_at", models.DateTimeField(blank=True, null=True)),
            ],
            options={
                "verbose_name": "Memory Projection",
                "verbose_name_plural": "Memory Projections",
                "db_table": "trader_memory_memoryprojection",
            },
        ),
        migrations.AddConstraint(
            model_name="memoryentry",
            constraint=models.UniqueConstraint(fields=("recommendation_id", "event_type", "occurred_at"), name="uq_memory_entry_unique"),
        ),
        migrations.AddIndex(
            model_name="memoryentry",
            index=models.Index(fields=("recommendation_id", "event_type"), name="trader_memo_recomme_6eb1be_idx"),
        ),
    ]
