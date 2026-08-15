"""Batch M3 — Backtest run API URL configuration."""

from __future__ import annotations

from django.urls import path

from apps.backtesting.interfaces.api.views import (
    BacktestRunDetailView,
    BacktestRunListCreateView,
    CostSensitivityView,
    EdgeValidationView,
    WalkForwardView,
)

urlpatterns = [
    path("runs/", BacktestRunListCreateView.as_view(), name="backtest-run-create"),
    path("runs/<uuid:run_id>/", BacktestRunDetailView.as_view(), name="backtest-run-detail"),
    path("walk-forward/", WalkForwardView.as_view(), name="backtest-walk-forward"),
    path("cost-sensitivity/", CostSensitivityView.as_view(), name="backtest-cost-sensitivity"),
    path("edge-validation/", EdgeValidationView.as_view(), name="backtest-edge-validation"),
]
