from __future__ import annotations

import uuid
from typing import Any

from rest_framework import status
from rest_framework.generics import GenericAPIView, ListAPIView
from rest_framework.request import Request
from rest_framework.response import Response

from apps.recommendations.application.recommendation_command_service import RecommendationCommandService
from apps.recommendations.application.recommendation_query_service import RecommendationQueryService
from apps.recommendations.domain.exceptions import IllegalTransition, RecommendationNotFound
from apps.recommendations.infrastructure.models import RecommendationExplanation
from apps.recommendations.interfaces.api.serializers import (
    RecommendationActionSerializer,
    RecommendationExplanationSerializer,
    RecommendationSerializer,
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


class RecommendationListView(ListAPIView):
    serializer_class = RecommendationSerializer

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self._query_service = RecommendationQueryService()

    def get(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        symbol = request.query_params.get("symbol")
        status_param = request.query_params.get("status")
        direction = request.query_params.get("direction")
        snapshots = self._query_service.list_recommendations(
            symbol=symbol,
            status=status_param,
            direction=direction,
        )
        serializer = self.get_serializer(snapshots, many=True)
        return Response(serializer.data)


class RecommendationDetailView(GenericAPIView):
    serializer_class = RecommendationSerializer

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self._query_service = RecommendationQueryService()

    def get(self, request: Request, pk: str, *args: Any, **kwargs: Any) -> Response:
        try:
            snapshot = self._query_service.get_recommendation(uuid.UUID(pk))
        except RecommendationNotFound:
            return Response(
                _problem_detail(
                    "recommendation-not-found",
                    f"Recommendation {pk} not found",
                    status.HTTP_404_NOT_FOUND,
                    request.path,
                ),
                status=status.HTTP_404_NOT_FOUND,
            )
        serializer = self.get_serializer(snapshot)
        return Response(serializer.data)


class RecommendationAcceptView(GenericAPIView):
    serializer_class = RecommendationActionSerializer

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self._command_service = RecommendationCommandService()

    def post(self, request: Request, pk: str, *args: Any, **kwargs: Any) -> Response:
        action_serializer = self.get_serializer(data=request.data)
        action_serializer.is_valid(raise_exception=True)
        try:
            aggregate = self._command_service.accept_recommendation(
                uuid.UUID(pk),
                reason=action_serializer.validated_data.get("reason", ""),
                changed_by=action_serializer.validated_data.get("changed_by", "user"),
            )
        except (RecommendationNotFound, IllegalTransition) as exc:
            return Response(
                _problem_detail(
                    type(exc).__name__,
                    str(exc),
                    status.HTTP_409_CONFLICT,
                    request.path,
                ),
                status=status.HTTP_409_CONFLICT,
            )
        return Response({"status": aggregate.status})


class RecommendationRejectView(GenericAPIView):
    serializer_class = RecommendationActionSerializer

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self._command_service = RecommendationCommandService()

    def post(self, request: Request, pk: str, *args: Any, **kwargs: Any) -> Response:
        action_serializer = self.get_serializer(data=request.data)
        action_serializer.is_valid(raise_exception=True)
        try:
            aggregate = self._command_service.reject_recommendation(
                uuid.UUID(pk),
                reason=action_serializer.validated_data.get("reason", ""),
                changed_by=action_serializer.validated_data.get("changed_by", "user"),
            )
        except (RecommendationNotFound, IllegalTransition) as exc:
            return Response(
                _problem_detail(
                    type(exc).__name__,
                    str(exc),
                    status.HTTP_409_CONFLICT,
                    request.path,
                ),
                status=status.HTTP_409_CONFLICT,
            )
        return Response({"status": aggregate.status})


class RecommendationExplanationView(GenericAPIView):
    serializer_class = RecommendationExplanationSerializer

    def get(self, request: Request, pk: str, *args: Any, **kwargs: Any) -> Response:
        try:
            explanation = RecommendationExplanation.objects.get(recommendation_id=uuid.UUID(pk))
        except RecommendationExplanation.DoesNotExist:
            return Response(
                _problem_detail(
                    "explanation-not-found",
                    f"Explanation for recommendation {pk} not found",
                    status.HTTP_404_NOT_FOUND,
                    request.path,
                ),
                status=status.HTTP_404_NOT_FOUND,
            )
        serializer = self.get_serializer(explanation)
        return Response(serializer.data)
