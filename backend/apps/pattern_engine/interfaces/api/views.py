from __future__ import annotations

import logging

from rest_framework.generics import ListAPIView, RetrieveAPIView
from rest_framework.pagination import LimitOffsetPagination

from apps.pattern_engine.infrastructure.models import (
    HistoricalFeatureVector,
    PatternAnalysisRun,
)
from apps.pattern_engine.interfaces.api.serializers import (
    HistoricalFeatureVectorSerializer,
    PatternAnalysisRunSerializer,
)

logger = logging.getLogger(__name__)


class PatternEnginePagination(LimitOffsetPagination):
    default_limit = 20
    max_limit = 200


class HistoricalFeatureVectorListView(ListAPIView):
    """GET /api/v1/pattern-engine/historical-vectors/?symbol=RELIANCE

    Lists precomputed historical feature vectors, newest first. ``symbol`` is
    optional; when omitted all symbols are returned (bounded by pagination).
    """

    serializer_class = HistoricalFeatureVectorSerializer
    pagination_class = PatternEnginePagination

    def get_queryset(self):
        qs = HistoricalFeatureVector.objects.all().order_by("-as_of")
        symbol = self.request.query_params.get("symbol")
        if symbol:
            qs = qs.filter(symbol=symbol.upper())
        return qs


class PatternAnalysisRunListView(ListAPIView):
    """GET /api/v1/pattern-engine/runs/?symbol=RELIANCE

    Lists persisted pattern analysis runs, newest first. ``symbol`` is
    optional.
    """

    serializer_class = PatternAnalysisRunSerializer
    pagination_class = PatternEnginePagination

    def get_queryset(self):
        qs = PatternAnalysisRun.objects.all().order_by("-as_of")
        symbol = self.request.query_params.get("symbol")
        if symbol:
            qs = qs.filter(symbol=symbol.upper())
        return qs


class PatternAnalysisRunDetailView(RetrieveAPIView):
    """GET /api/v1/pattern-engine/runs/<uuid>/

    Returns the rich, persisted result of a single pattern analysis run.
    """

    serializer_class = PatternAnalysisRunSerializer
    lookup_url_kwarg = "run_id"
    queryset = PatternAnalysisRun.objects.all()


__all__ = [
    "HistoricalFeatureVectorListView",
    "PatternAnalysisRunDetailView",
    "PatternAnalysisRunListView",
]
