import uuid

from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True

    dependencies = []

    operations = [
        migrations.CreateModel(
            name="TradingStrategy",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("created_at", models.DateTimeField(auto_now_add=True, db_index=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("is_deleted", models.BooleanField(db_index=True, default=False)),
                ("deleted_at", models.DateTimeField(blank=True, null=True)),
                ("name", models.CharField(max_length=128, unique=True)),
                (
                    "status",
                    models.CharField(
                        choices=[("ACTIVE", "Active"), ("INACTIVE", "Inactive"), ("RETIRED", "Retired")],
                        db_index=True,
                        default="INACTIVE",
                        max_length=16,
                    ),
                ),
                ("priority", models.IntegerField(db_index=True, default=0)),
                ("symbol_filter", models.CharField(blank=True, max_length=20, null=True)),
                ("sector_filter", models.CharField(blank=True, max_length=64, null=True)),
                (
                    "preferred_provider",
                    models.CharField(
                        blank=True,
                        choices=[
                            ("gemini", "GEMINI"),
                            ("openai", "OPENAI"),
                            ("claude", "CLAUDE"),
                            ("ollama", "OLLAMA"),
                            ("deepseek", "DEEPSEEK"),
                        ],
                        max_length=32,
                        null=True,
                    ),
                ),
                ("confidence_threshold", models.DecimalField(decimal_places=4, default=0.6, max_digits=5)),
                ("risk_threshold", models.DecimalField(decimal_places=4, default=0.5, max_digits=5)),
            ],
            options={
                "verbose_name": "Trading Strategy",
                "verbose_name_plural": "Trading Strategies",
                "ordering": ["priority", "created_at"],
            },
        ),
    ]
