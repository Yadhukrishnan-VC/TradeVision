from __future__ import annotations

from django.urls import re_path

from apps.dashboard.interfaces.websocket.analytics_risk.consumers import PnLConsumer, RiskConsumer

websocket_urlpatterns = [
    re_path(
        r"ws/dashboard/accounts/(?P<account_id>[0-9a-f-]+)/pnl/$",
        PnLConsumer.as_asgi(),
    ),
    re_path(
        r"ws/dashboard/accounts/(?P<account_id>[0-9a-f-]+)/risk/$",
        RiskConsumer.as_asgi(),
    ),
]
