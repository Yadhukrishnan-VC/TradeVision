from __future__ import annotations

from django.urls import path

from apps.watchlist.interfaces.api.views import (
    WatchlistItemView,
    WatchlistListView,
    WatchlistReorderView,
)

app_name = "watchlist"

urlpatterns = [
    path("", WatchlistListView.as_view(), name="watchlist-list"),
    path("reorder/", WatchlistReorderView.as_view(), name="watchlist-reorder"),
    path("<int:instrument_token>/", WatchlistItemView.as_view(), name="watchlist-item"),
]
