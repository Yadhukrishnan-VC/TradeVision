from __future__ import annotations

from django.urls import path

from apps.trader_memory.interfaces.api.views import (
    MemoryEntryListView,
    MemoryProjectionDetailView,
)

urlpatterns = [
    path("entries/", MemoryEntryListView.as_view(), name="memory-entry-list"),
    path("projections/<str:strategy_id>/", MemoryProjectionDetailView.as_view(), name="memory-projection-detail"),
]
