from __future__ import annotations

from django.urls import path

from apps.signals_engine.interfaces.api.views import SignalDetailView, SignalListCreateView

urlpatterns = [
    path("", SignalListCreateView.as_view(), name="signal-list"),
    path("<uuid:pk>/", SignalDetailView.as_view(), name="signal-detail"),
]
