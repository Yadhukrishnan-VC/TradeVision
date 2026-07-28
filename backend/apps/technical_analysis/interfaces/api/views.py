from __future__ import annotations

import json
import logging
import uuid
from typing import Any

from django.conf import settings
from rest_framework import status
from rest_framework.generics import GenericAPIView
from rest_framework.request import Request
from rest_framework.response import Response

from apps.common.domain.value_objects import IdempotencyKey
from apps.eventbus.infrastructure.event_bus_factory import get_event_bus
from apps.technical_analysis.application.services import (
    TechnicalAnalysisIngestionService,
)
from apps.technical_analysis.infrastructure.repositories import (
    TASnapshotRepository,
)
from apps.technical_analysis.interfaces.api.serializers import (
    TechnicalAnalysisResponseSerializer,
)

logger = logging.getLogger(__name__)


class TradingViewTechnicalAnalysisWebhookView(GenericAPIView):
    """Receive TradingView Pine Script technical analysis alert webhooks.

    POST /api/v1/technical-analysis/webhooks/tradingview/{token}/

    The URL token must match ``settings.TRADINGVIEW_TA_WEBHOOK_TOKEN``.
    On successful validation, the payload is normalised, persisted
    as a ``TASnapshot``, and a ``technical_analysis.TechnicalAnalysisCompleted``
    event is published.

    Responses:
        ``202``: Payload accepted and snapshot created.
        ``401``: Invalid token.
        ``400``: Malformed or invalid payload.
        ``501``: Webhook not configured.
    """

    permission_classes: list[Any] = []
    authentication_classes: list[Any] = []

    # Constructed once per process, not per request
    _repository: TASnapshotRepository | None = None
    _event_bus: Any = None

    @classmethod
    def _get_repository(cls) -> TASnapshotRepository:
        if cls._repository is None:
            cls._repository = TASnapshotRepository()
        return cls._repository

    @classmethod
    def _get_event_bus(cls) -> Any:
        if cls._event_bus is None:
            cls._event_bus = get_event_bus()
        return cls._event_bus

    def post(self, request: Request, token: str) -> Response:
        expected_token = getattr(settings, "TRADINGVIEW_TA_WEBHOOK_TOKEN", "")
        if not expected_token:
            logger.error("TRADINGVIEW_TA_WEBHOOK_TOKEN not configured")
            return Response(
                {"error": "Webhook not configured"},
                status=status.HTTP_501_NOT_IMPLEMENTED,
            )

        if token != expected_token:
            logger.warning(
                "tradingview_ta_webhook_invalid_token",
                extra={"provided_token": token[:8] + "..." if len(token) > 8 else token},
            )
            return Response(
                {"error": "Invalid token"},
                status=status.HTTP_401_UNAUTHORIZED,
            )

        try:
            payload = json.loads(request.body)
        except (json.JSONDecodeError, UnicodeDecodeError) as exc:
            logger.warning(
                "tradingview_ta_webhook_invalid_json",
                extra={"error": str(exc)},
            )
            return Response(
                {"error": f"Invalid JSON body: {exc}"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        if not isinstance(payload, dict):
            return Response(
                {"error": "Payload must be a JSON object"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        alert_id = payload.get("alert_id") or payload.get("id") or ""
        correlation_source = f"tradingview_ta:{alert_id}"
        correlation_id = uuid.UUID(
            hex=IdempotencyKey.generate(correlation_source).value[:32],
        )

        service = TechnicalAnalysisIngestionService(
            repository=self._get_repository(),
            event_bus=self._get_event_bus(),
        )

        try:
            snapshot = service.ingest(
                raw_payload=payload,
                correlation_id=correlation_id,
            )
        except Exception as exc:
            logger.warning(
                "tradingview_ta_webhook_ingest_failed",
                extra={"error": str(exc)},
            )
            return Response(
                {"error": f"Ingestion failed: {exc}"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        serializer = TechnicalAnalysisResponseSerializer({
            "status": "accepted",
            "snapshot_id": snapshot.id,
        })
        return Response(serializer.data, status=status.HTTP_202_ACCEPTED)
