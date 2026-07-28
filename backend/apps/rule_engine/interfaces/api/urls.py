from __future__ import annotations

from django.urls import path

from apps.rule_engine.interfaces.api.views import (
    RuleConfigDetailView,
    RuleConfigListView,
    RuleExecutionListView,
)

urlpatterns = [
    path("configs/", RuleConfigListView.as_view(), name="rule-config-list"),
    path("configs/<str:rule_id>/", RuleConfigDetailView.as_view(), name="rule-config-detail"),
    path("executions/", RuleExecutionListView.as_view(), name="rule-execution-list"),
]
