from __future__ import annotations

from django.urls import path

from apps.ingestion.interfaces.api.views import (
    ChartinkWebhookView,
    RawWebhookEventListView,
    TradingViewWebhookView,
)

app_name = "ingestion"

urlpatterns = [
    path(
        "webhooks/tradingview/<str:token>/",
        TradingViewWebhookView.as_view(),
        name="tradingview-webhook",
    ),
    path(
        "webhooks/chartink/<str:token>/",
        ChartinkWebhookView.as_view(),
        name="chartink-webhook",
    ),
    path(
        "raw-events/",
        RawWebhookEventListView.as_view(),
        name="raw-event-list",
    ),
]
