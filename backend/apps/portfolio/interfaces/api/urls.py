from __future__ import annotations

from django.urls import path

from apps.portfolio.interfaces.api.views import (
    PortfolioSummaryView,
    PositionsListView,
    RecordFillView,
    SetDailyCapitalView,
)

urlpatterns = [
    path("", PortfolioSummaryView.as_view(), name="portfolio-summary"),
    path("positions/", PositionsListView.as_view(), name="portfolio-positions"),
    path("fills/", RecordFillView.as_view(), name="portfolio-fill-record"),
    path("capital/daily/", SetDailyCapitalView.as_view(), name="set-daily-capital"),
]
