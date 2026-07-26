from __future__ import annotations

from django.db import migrations, models


class Migration(migrations.Migration):
    initial = True

    dependencies: list[tuple[str, str]] = []

    operations = [
        migrations.CreateModel(
            name="PnLSnapshot",
            fields=[
                ("id", models.UUIDField(primary_key=True)),
                ("account_id", models.UUIDField(db_index=True)),
                ("snapshot_at", models.DateTimeField()),
                ("realized_pnl", models.DecimalField(decimal_places=8, default=0, max_digits=20)),
                ("unrealized_pnl", models.DecimalField(decimal_places=8, default=0, max_digits=20)),
                ("total_pnl", models.DecimalField(decimal_places=8, default=0, max_digits=20)),
                ("cumulative_pnl", models.DecimalField(decimal_places=8, default=0, max_digits=20)),
                ("peak_cumulative_pnl", models.DecimalField(decimal_places=8, default=0, max_digits=20)),
                ("drawdown_pct", models.DecimalField(decimal_places=4, default=0, max_digits=10)),
                ("last_event_id", models.UUIDField(blank=True, null=True)),
            ],
            options={
                "db_table": "dashboard_pnl_snapshot",
            },
        ),
        migrations.AddIndex(
            model_name="pnlsnapshot",
            index=models.Index(fields=["account_id", "-snapshot_at"], name=None),
        ),
        migrations.CreateModel(
            name="PnLDailyRollup",
            fields=[
                ("id", models.UUIDField(primary_key=True)),
                ("account_id", models.UUIDField(db_index=True)),
                ("trading_date", models.DateField()),
                ("realized_pnl", models.DecimalField(decimal_places=8, default=0, max_digits=20)),
                ("unrealized_pnl", models.DecimalField(decimal_places=8, default=0, max_digits=20)),
                ("total_pnl", models.DecimalField(decimal_places=8, default=0, max_digits=20)),
                ("cumulative_pnl", models.DecimalField(decimal_places=8, default=0, max_digits=20)),
                ("peak_cumulative_pnl", models.DecimalField(decimal_places=8, default=0, max_digits=20)),
                ("drawdown_pct", models.DecimalField(decimal_places=4, default=0, max_digits=10)),
            ],
            options={
                "db_table": "dashboard_pnl_daily_rollup",
            },
        ),
        migrations.AddConstraint(
            model_name="pnldailyrollup",
            constraint=models.UniqueConstraint(fields=["account_id", "trading_date"], name="uq_pnl_daily_account_date"),
        ),
        migrations.CreateModel(
            name="PerformanceSnapshot",
            fields=[
                ("id", models.UUIDField(primary_key=True)),
                ("account_id", models.UUIDField(db_index=True)),
                ("period", models.CharField(max_length=10)),
                ("computed_at", models.DateTimeField(auto_now=True)),
                ("win_rate", models.DecimalField(decimal_places=4, default=0, max_digits=6)),
                ("avg_win", models.DecimalField(decimal_places=8, default=0, max_digits=20)),
                ("avg_loss", models.DecimalField(decimal_places=8, default=0, max_digits=20)),
                ("profit_factor", models.DecimalField(blank=True, decimal_places=4, max_digits=10, null=True)),
                ("expectancy", models.DecimalField(decimal_places=8, default=0, max_digits=20)),
                ("sharpe_like_ratio", models.DecimalField(blank=True, decimal_places=4, max_digits=10, null=True)),
                ("total_trades", models.IntegerField(default=0)),
                ("winning_trades", models.IntegerField(default=0)),
                ("losing_trades", models.IntegerField(default=0)),
            ],
            options={
                "db_table": "dashboard_performance_snapshot",
            },
        ),
        migrations.AddConstraint(
            model_name="performancesnapshot",
            constraint=models.UniqueConstraint(fields=["account_id", "period"], name="uq_performance_account_period"),
        ),
        migrations.CreateModel(
            name="RiskMetricSnapshot",
            fields=[
                ("id", models.UUIDField(primary_key=True)),
                ("account_id", models.UUIDField(db_index=True)),
                ("snapshot_at", models.DateTimeField()),
                ("total_exposure", models.DecimalField(decimal_places=8, default=0, max_digits=20)),
                ("largest_position_pct", models.DecimalField(decimal_places=4, default=0, max_digits=6)),
                ("sector_concentration_pct", models.DecimalField(decimal_places=4, default=0, max_digits=6)),
                ("leverage_ratio", models.DecimalField(decimal_places=4, default=0, max_digits=10)),
            ],
            options={
                "db_table": "dashboard_risk_metric_snapshot",
            },
        ),
        migrations.AddIndex(
            model_name="riskmetricsnapshot",
            index=models.Index(fields=["account_id", "-snapshot_at"], name=None),
        ),
        migrations.CreateModel(
            name="RiskAlertProjection",
            fields=[
                ("alert_id", models.UUIDField(primary_key=True)),
                ("account_id", models.UUIDField(db_index=True)),
                ("alert_type", models.CharField(max_length=50)),
                ("severity", models.CharField(max_length=20)),
                ("message", models.TextField()),
                ("raised_at", models.DateTimeField()),
                ("resolved_at", models.DateTimeField(blank=True, null=True)),
                ("last_event_id", models.UUIDField(blank=True, null=True)),
            ],
            options={
                "db_table": "dashboard_risk_alert_projection",
            },
        ),
        migrations.AddIndex(
            model_name="riskalertprojection",
            index=models.Index(fields=["account_id", "-raised_at"], name=None),
        ),
    ]
