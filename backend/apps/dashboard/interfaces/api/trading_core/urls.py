from __future__ import annotations

from django.urls import path

from apps.dashboard.interfaces.api.trading_core.views import (
    ClosedTradesListView,
    DashboardHomeSummaryView,
    HoldingDetailView,
    LivePositionDetailView,
    LivePositionsListView,
    OrderDetailView,
    OrdersListView,
    OpenTradesListView,
    PortfolioCompositionView,
    TradeExportStatusView,
    TradeExportView,
    TradeHistoryListView,
)

urlpatterns = [
    path("home/summary/", DashboardHomeSummaryView.as_view(), name="dashboard-home-summary"),
    path("portfolio/composition/", PortfolioCompositionView.as_view(), name="portfolio-composition"),
    path("portfolio/holdings/<str:symbol>/", HoldingDetailView.as_view(), name="holding-detail"),
    path("positions/live/", LivePositionsListView.as_view(), name="live-positions-list"),
    path("positions/live/<str:position_id>/", LivePositionDetailView.as_view(), name="live-position-detail"),
    path("orders/", OrdersListView.as_view(), name="orders-list"),
    path("orders/<str:order_id>/", OrderDetailView.as_view(), name="order-detail"),
    path("trades/history/", TradeHistoryListView.as_view(), name="trade-history-list"),
    path("trades/history/export/", TradeExportView.as_view(), name="trade-history-export"),
    path("trades/history/export/<str:export_id>/", TradeExportStatusView.as_view(), name="trade-export-status"),
    path("trades/open/", OpenTradesListView.as_view(), name="open-trades-list"),
    path("trades/closed/", ClosedTradesListView.as_view(), name="closed-trades-list"),
]
