"""NEWS-FEED-1 — API views."""

from __future__ import annotations

from django.db.models import QuerySet
from rest_framework.generics import ListAPIView, RetrieveAPIView

from apps.news_feed.infrastructure.models import NewsItem
from apps.news_feed.interfaces.api.serializers import NewsItemSerializer


class NewsItemListView(ListAPIView):
    """List ingested news (read-only). Optional ``?symbol=`` filter.

    Pagination follows the global ``PageNumberPagination`` envelope
    (``{count, next, previous, results}``, PAGE_SIZE=20).
    """

    serializer_class = NewsItemSerializer

    def get_queryset(self) -> QuerySet:
        qs = NewsItem.objects.all().order_by("-published_at")
        symbol = self.request.query_params.get("symbol")
        if symbol:
            qs = qs.filter(symbols__contains=[symbol])
        return qs


class NewsItemDetailView(RetrieveAPIView):
    """Retrieve one ingested news item (read-only)."""

    serializer_class = NewsItemSerializer
    queryset = NewsItem.objects.all()
