from __future__ import annotations

from django.urls import path

from apps.technical_analysis.interfaces.api.views import (
    TradingViewTechnicalAnalysisWebhookView,
)

app_name = "technical_analysis"

urlpatterns = [
    path(
        "webhooks/tradingview/<str:token>/",
        TradingViewTechnicalAnalysisWebhookView.as_view(),
        name="tradingview-ta-webhook",
    ),
]
