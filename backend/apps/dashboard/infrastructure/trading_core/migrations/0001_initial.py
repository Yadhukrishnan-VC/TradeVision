from __future__ import annotations

from django.db import migrations, models


class Migration(migrations.Migration):
    initial = True

    dependencies: list[tuple[str, str]] = []

    operations = [
        migrations.CreateModel(
            name="DashboardHomeSummary",
            fields=[
                ("projection_version", models.IntegerField(default=0)),
                ("projection_updated_at", models.DateTimeField(null=True, blank=True)),
                ("last_event_id", models.UUIDField(null=True, blank=True)),
                ("last_event_version", models.IntegerField(default=0)),
                ("account_id", models.UUIDField(primary_key=True, serialize=False)),
                ("open_positions_count", models.IntegerField(default=0)),
                ("open_orders_count", models.IntegerField(default=0)),
                ("today_realized_pnl", models.DecimalField(decimal_places=8, default=0, max_digits=20)),
                ("today_unrealized_pnl", models.DecimalField(decimal_places=8, default=0, max_digits=20)),
                ("active_alerts_count", models.IntegerField(default=0)),
                ("broker_connection_status", models.CharField(default="disconnected", max_length=20)),
                ("market_session_status", models.CharField(default="closed", max_length=20)),
            ],
            options={
                "db_table": "dashboard_homesummary",
            },
        ),
        migrations.CreateModel(
            name="ExportJob",
            fields=[
                ("export_id", models.UUIDField(primary_key=True, serialize=False)),
                ("account_id", models.UUIDField(db_index=True)),
                ("status", models.CharField(default="pending", max_length=20)),
                ("format", models.CharField(max_length=10)),
                ("file_url", models.URLField(null=True, blank=True)),
                ("requested_at", models.DateTimeField(auto_now_add=True)),
                ("completed_at", models.DateTimeField(null=True, blank=True)),
                ("error_message", models.TextField(null=True, blank=True)),
            ],
            options={
                "db_table": "dashboard_exportjob",
            },
        ),
        migrations.CreateModel(
            name="Holding",
            fields=[
                ("projection_version", models.IntegerField(default=0)),
                ("projection_updated_at", models.DateTimeField(null=True, blank=True)),
                ("last_event_id", models.UUIDField(null=True, blank=True)),
                ("last_event_version", models.IntegerField(default=0)),
                ("id", models.UUIDField(primary_key=True, serialize=False)),
                ("account_id", models.UUIDField(db_index=True)),
                ("symbol", models.CharField(max_length=20)),
                ("quantity", models.DecimalField(decimal_places=8, max_digits=20)),
                ("avg_cost", models.DecimalField(decimal_places=8, max_digits=20)),
                ("cost_basis", models.DecimalField(decimal_places=8, max_digits=20)),
                ("opened_at", models.DateTimeField()),
            ],
            options={
                "db_table": "dashboard_holding",
            },
        ),
        migrations.CreateModel(
            name="OrderSnapshot",
            fields=[
                ("projection_version", models.IntegerField(default=0)),
                ("projection_updated_at", models.DateTimeField(null=True, blank=True)),
                ("last_event_id", models.UUIDField(null=True, blank=True)),
                ("last_event_version", models.IntegerField(default=0)),
                ("order_id", models.UUIDField(primary_key=True, serialize=False)),
                ("account_id", models.UUIDField(db_index=True)),
                ("symbol", models.CharField(max_length=20)),
                ("side", models.CharField(max_length=4)),
                ("order_type", models.CharField(max_length=10)),
                ("status", models.CharField(max_length=20)),
                ("quantity", models.DecimalField(decimal_places=8, max_digits=20)),
                ("filled_quantity", models.DecimalField(decimal_places=8, default=0, max_digits=20)),
                ("avg_fill_price", models.DecimalField(decimal_places=8, max_digits=20, null=True, blank=True)),
                ("limit_price", models.DecimalField(decimal_places=8, max_digits=20, null=True, blank=True)),
                ("placed_at", models.DateTimeField()),
            ],
            options={
                "db_table": "dashboard_ordersnapshot",
            },
        ),
        migrations.CreateModel(
            name="PositionSnapshot",
            fields=[
                ("projection_version", models.IntegerField(default=0)),
                ("projection_updated_at", models.DateTimeField(null=True, blank=True)),
                ("last_event_id", models.UUIDField(null=True, blank=True)),
                ("last_event_version", models.IntegerField(default=0)),
                ("position_id", models.UUIDField(primary_key=True, serialize=False)),
                ("account_id", models.UUIDField(db_index=True)),
                ("symbol", models.CharField(max_length=20)),
                ("side", models.CharField(max_length=4)),
                ("quantity", models.DecimalField(decimal_places=8, max_digits=20)),
                ("entry_price", models.DecimalField(decimal_places=8, max_digits=20)),
                ("is_open", models.BooleanField(default=True)),
                ("opened_at", models.DateTimeField()),
                ("closed_at", models.DateTimeField(null=True, blank=True)),
            ],
            options={
                "db_table": "dashboard_positionsnapshot",
            },
        ),
        migrations.CreateModel(
            name="TradeRecord",
            fields=[
                ("projection_version", models.IntegerField(default=0)),
                ("projection_updated_at", models.DateTimeField(null=True, blank=True)),
                ("last_event_id", models.UUIDField(null=True, blank=True)),
                ("last_event_version", models.IntegerField(default=0)),
                ("trade_id", models.UUIDField(primary_key=True, serialize=False)),
                ("account_id", models.UUIDField(db_index=True)),
                ("symbol", models.CharField(max_length=20)),
                ("side", models.CharField(max_length=4)),
                ("entry_price", models.DecimalField(decimal_places=8, max_digits=20)),
                ("exit_price", models.DecimalField(decimal_places=8, max_digits=20)),
                ("quantity", models.DecimalField(decimal_places=8, max_digits=20)),
                ("realized_pnl", models.DecimalField(decimal_places=8, max_digits=20)),
                ("realized_pnl_pct", models.DecimalField(decimal_places=4, max_digits=10)),
                ("opened_at", models.DateTimeField()),
                ("closed_at", models.DateTimeField()),
                ("holding_period_seconds", models.IntegerField()),
            ],
            options={
                "db_table": "dashboard_traderecord",
            },
        ),
        migrations.CreateModel(
            name="EventLog",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("event_id", models.UUIDField(db_index=True)),
                ("projector", models.CharField(max_length=255)),
                ("applied_at", models.DateTimeField(auto_now_add=True)),
            ],
            options={
                "db_table": "dashboard_eventlog",
            },
        ),
        migrations.AddConstraint(
            model_name="eventlog",
            constraint=models.UniqueConstraint(fields=("event_id", "projector"), name="uq_dashboard_eventlog_event_projector"),
        ),
        migrations.AddConstraint(
            model_name="holding",
            constraint=models.UniqueConstraint(fields=("account_id", "symbol"), name="uq_holding_account_symbol"),
        ),
        migrations.AddConstraint(
            model_name="traderecord",
            constraint=models.UniqueConstraint(fields=("last_event_id",), name="uq_traderecord_last_event_id"),
        ),
        migrations.AddIndex(
            model_name="positionsnapshot",
            index=models.Index(fields=["account_id", "is_open"], name="idx_positions_account_open"),
        ),
        migrations.AddIndex(
            model_name="positionsnapshot",
            index=models.Index(fields=["account_id", "symbol"], name="idx_positions_account_symbol"),
        ),
        migrations.AddIndex(
            model_name="ordersnapshot",
            index=models.Index(fields=["account_id", "status", "placed_at"], name="idx_orders_acct_status_placed"),
        ),
        migrations.AddIndex(
            model_name="ordersnapshot",
            index=models.Index(fields=["account_id", "symbol", "placed_at"], name="idx_orders_account_symbol_placed"),
        ),
        migrations.AddIndex(
            model_name="traderecord",
            index=models.Index(fields=["account_id", "closed_at"], name="idx_trades_account_closed"),
        ),
        migrations.AddIndex(
            model_name="traderecord",
            index=models.Index(fields=["account_id", "symbol", "closed_at"], name="idx_trades_account_symbol_closed"),
        ),
        migrations.AddIndex(
            model_name="traderecord",
            index=models.Index(fields=["account_id", "realized_pnl"], name="idx_trades_account_pnl"),
        ),
        migrations.AddIndex(
            model_name="holding",
            index=models.Index(fields=["account_id", "quantity"], name="idx_holding_account_qty"),
        ),
        migrations.AddIndex(
            model_name="exportjob",
            index=models.Index(fields=["account_id", "status"], name="idx_exportjob_account_status"),
        ),
        migrations.AddIndex(
            model_name="eventlog",
            index=models.Index(fields=["event_id", "projector"], name="idx_eventlog_event_projector"),
        ),
    ]
