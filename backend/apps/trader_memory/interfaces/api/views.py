from __future__ import annotations

import uuid
from typing import Any

from rest_framework import status
from rest_framework.generics import GenericAPIView, ListAPIView
from rest_framework.request import Request
from rest_framework.response import Response

from apps.trader_memory.application.memory_query_service import MemoryQueryService
from apps.trader_memory.domain.exceptions import MemoryEntryNotFound
from apps.trader_memory.interfaces.api.serializers import (
    MemoryEntrySerializer,
    MemoryProjectionSerializer,
)


def _problem_detail(
    exc_type: str, title: str, status_code: int, instance: str
) -> dict[str, Any]:
    return {
        "type": f"urn:tradevision:error:{exc_type}",
        "title": title,
        "status": status_code,
        "instance": instance,
    }


class MemoryEntryListView(ListAPIView):
    serializer_class = MemoryEntrySerializer

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self._service = MemoryQueryService()

    def get(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        recommendation_id = request.query_params.get("recommendation_id")
        event_type = request.query_params.get("event_type")
        snapshots = self._service.list_entries(
            recommendation_id=recommendation_id,
            event_type=event_type,
        )
        serializer = self.get_serializer(snapshots, many=True)
        return Response(serializer.data)


class MemoryProjectionDetailView(GenericAPIView):
    serializer_class = MemoryProjectionSerializer

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self._service = MemoryQueryService()

    def get(self, request: Request, strategy_id: str, *args: Any, **kwargs: Any) -> Response:
        try:
            snapshot = self._service.get_projection(uuid.UUID(strategy_id))
        except MemoryEntryNotFound:
            return Response(
                _problem_detail(
                    "projection-not-found",
                    f"Projection for strategy {strategy_id} not found",
                    status.HTTP_404_NOT_FOUND,
                    request.path,
                ),
                status=status.HTTP_404_NOT_FOUND,
            )
        serializer = self.get_serializer(snapshot)
        return Response(serializer.data)
