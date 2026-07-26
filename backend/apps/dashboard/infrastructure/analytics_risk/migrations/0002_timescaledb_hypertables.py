from __future__ import annotations

from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [
        ("dashboard", "0001_initial"),
    ]

    operations = [
        migrations.RunSQL(
            sql="SELECT create_hypertable('dashboard_pnl_snapshot', 'snapshot_at', if_not_exists => TRUE);",
            reverse_sql="SELECT 1;",
        ),
        migrations.RunSQL(
            sql="SELECT create_hypertable('dashboard_risk_metric_snapshot', 'snapshot_at', if_not_exists => TRUE);",
            reverse_sql="SELECT 1;",
        ),
    ]
