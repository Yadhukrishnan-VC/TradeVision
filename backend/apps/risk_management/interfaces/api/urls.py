from __future__ import annotations

from django.urls import path

from apps.risk_management.interfaces.api.views import (
    KillSwitchActivateView,
    KillSwitchDeactivateView,
    KillSwitchListView,
    RiskDecisionListView,
)

urlpatterns = [
    path("decisions/", RiskDecisionListView.as_view(), name="risk-decision-list"),
    path(
        "kill-switch/",
        KillSwitchListView.as_view(),
        name="kill-switch-list",
    ),
    path(
        "kill-switch/activate/",
        KillSwitchActivateView.as_view(),
        name="kill-switch-activate",
    ),
    path(
        "kill-switch/deactivate/",
        KillSwitchDeactivateView.as_view(),
        name="kill-switch-deactivate",
    ),
]
