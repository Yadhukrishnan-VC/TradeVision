from __future__ import annotations

from django.urls import re_path

from apps.dashboard.interfaces.websocket.trading_core.consumers import (
    DashboardHomeConsumer,
    DashboardOrdersConsumer,
    DashboardPortfolioConsumer,
    DashboardPositionsConsumer,
)

websocket_urlpatterns = [
    re_path(r"ws/dashboard/home/$", DashboardHomeConsumer.as_asgi()),
    re_path(r"ws/dashboard/portfolio/$", DashboardPortfolioConsumer.as_asgi()),
    re_path(r"ws/dashboard/positions/live/$", DashboardPositionsConsumer.as_asgi()),
    re_path(r"ws/dashboard/orders/$", DashboardOrdersConsumer.as_asgi()),
]
