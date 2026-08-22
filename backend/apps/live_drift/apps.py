from __future__ import annotations

from django.apps import AppConfig


class LiveDriftConfig(AppConfig):
    """Django AppConfig for the ``live_drift`` app (LIVE-PAPER-DRESS-REHEARSAL-1).

    Bridges "validated in a backtest" and "trusted with real capital": rules
    the owner explicitly flags as under observation may fire on the paper
    broker against live data, and a monitor compares their live paper-trade
    statistics with their recorded backtest baselines.
    """

    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.live_drift"
    label = "live_drift"
    verbose_name = "Live Drift Monitor"
