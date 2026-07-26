from __future__ import annotations

from django.urls import path

from apps.market_data.interfaces.api.views import (
    CandleListView,
    InstrumentSearchView,
    MarketDataHealthView,
    MarketSessionView,
)

app_name = "market_data"

urlpatterns = [
    path(
        "instruments/",
        InstrumentSearchView.as_view(),
        name="instrument-search",
    ),
    path(
        "candles/<str:symbol>/",
        CandleListView.as_view(),
        name="candle-list",
    ),
    path(
        "session/",
        MarketSessionView.as_view(),
        name="market-session",
    ),
    path(
        "health/",
        MarketDataHealthView.as_view(),
        name="market-data-health",
    ),
]
