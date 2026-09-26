from __future__ import annotations

from typing import Any

from rest_framework import status
from rest_framework.generics import GenericAPIView, ListCreateAPIView
from rest_framework.request import Request
from rest_framework.response import Response

from apps.strategy_registry.interfaces.api.serializers import (
    StrategySymbolAffinitySerializer,
    TradingStrategyCreateSerializer,
    TradingStrategySerializer,
    TradingStrategyUpdateSerializer,
)
from apps.strategy_registry.models import StrategySymbolAffinity, TradingStrategy


class StrategyListView(ListCreateAPIView):
    """List active trading strategies or create a new one."""

    serializer_class = TradingStrategySerializer
    serializer_create_class = TradingStrategyCreateSerializer

    def get_queryset(self):
        qs = TradingStrategy.objects.filter(is_deleted=False)
        status_param = self.request.query_params.get("status")
        if status_param:
            qs = qs.filter(status=status_param.upper())
        return qs.order_by("priority", "created_at")

    def list(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        queryset = self.get_queryset()
        serializer = self.get_serializer(queryset, many=True)
        return Response(serializer.data)

    def create(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        serializer = self.serializer_create_class(data=request.data)
        serializer.is_valid(raise_exception=True)
        instance = serializer.save()
        out = TradingStrategySerializer(instance)
        return Response(out.data, status=status.HTTP_201_CREATED)


class StrategyDetailView(GenericAPIView):
    """Read, update or soft-delete a single trading strategy."""

    serializer_class = TradingStrategySerializer
    serializer_update_class = TradingStrategyUpdateSerializer

    def get_object(self) -> TradingStrategy:
        pk = self.kwargs["pk"]
        return TradingStrategy.objects.get(id=pk, is_deleted=False)

    def get(self, request: Request, pk: str, *args: Any, **kwargs: Any) -> Response:
        instance = self.get_object()
        serializer = self.get_serializer(instance)
        return Response(serializer.data)

    def patch(self, request: Request, pk: str, *args: Any, **kwargs: Any) -> Response:
        instance = self.get_object()
        serializer = self.serializer_update_class(
            instance, data=request.data, partial=True
        )
        serializer.is_valid(raise_exception=True)
        serializer.save()
        out = self.get_serializer(instance)
        return Response(out.data)

    def delete(self, request: Request, pk: str, *args: Any, **kwargs: Any) -> Response:
        instance = self.get_object()
        instance.is_deleted = True
        instance.save(update_fields=["is_deleted", "updated_at"])
        return Response(status=status.HTTP_204_NO_CONTENT)


class StrategySymbolAffinityListView(ListCreateAPIView):
    """Per-symbol strategy rankings (evidence-backed backtest affinities).

    ``GET /api/v1/strategies/affinities/?symbol=TCS`` returns every strategy
    with backtest evidence for that symbol, ordered best-first. Without
    ``?symbol=``* the full table is returned.
    """

    serializer_class = StrategySymbolAffinitySerializer

    def get_queryset(self):
        qs = StrategySymbolAffinity.objects.select_related("strategy").filter(
            strategy__is_deleted=False
        )
        symbol = self.request.query_params.get("symbol")
        if symbol:
            qs = qs.filter(symbol=str(symbol).strip().upper())
        return qs.order_by("symbol", "rank")