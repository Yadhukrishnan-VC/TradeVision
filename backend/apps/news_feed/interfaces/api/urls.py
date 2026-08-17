"""NEWS-FEED-1 — API routes."""

from __future__ import annotations

from django.urls import path

from apps.news_feed.interfaces.api.views import NewsItemDetailView, NewsItemListView

urlpatterns = [
    path("", NewsItemListView.as_view(), name="news-item-list"),
    path("<uuid:pk>/", NewsItemDetailView.as_view(), name="news-item-detail"),
]
