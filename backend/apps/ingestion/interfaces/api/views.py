from __future__ import annotations

import json
import logging
import uuid
from typing import Any

from django.conf import settings
from rest_framework import status
from rest_framework.generics import GenericAPIView, ListAPIView
from rest_framework.permissions import IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response

from apps.accounts.infrastructure.permissions import IsStaffRole
from apps.common.domain.value_objects import IdempotencyKey
from apps.eventbus.domain.events import DomainEvent
from apps.eventbus.infrastructure.event_bus_factory import get_event_bus
from apps.ingestion.application.services import (
    TradingViewPayloadParser,
    WebhookSignatureVerifier,
)
from apps.ingestion.domain.value_objects import WebhookSource
from apps.ingestion.infrastructure.models import RawWebhookEvent
from apps.ingestion.infrastructure.repositories import RawWebhookEventRepository
from apps.ingestion.interfaces.api.serializers import (
    RawWebhookEventSerializer,
    WebhookResponseSerializer,
)

logger = logging.getLogger(__name__)


class TradingViewWebhookView(GenericAPIView):
    """Receive TradingView Pine Script alert webhooks.

    POST /api/v1/ingestion/webhooks/tradingview/{token}/

    The URL token must match ``settings.TRADINGVIEW_WEBHOOK_TOKEN``.
    On successful signature verification, the payload is persisted as a
    ``RawWebhookEvent`` and an ``ingestion.RawAlertReceived`` event is
    published.

    Responses:
        ``202``: Webhook accepted.
        ``401``: Invalid token or signature.
        ``400``: Malformed payload.
    """

    permission_classes: list[Any] = []  # Auth via URL token + IP allowlist
    authentication_classes: list[Any] = []

    def post(self, request: Request, token: str) -> Response:
        verifier = WebhookSignatureVerifier(
            allowed_ips=getattr(settings, "TRADINGVIEW_ALLOWED_IPS", None),
        )

        expected_token = getattr(settings, "TRADINGVIEW_WEBHOOK_TOKEN", "")
        if not expected_token:
            logger.error("TRADINGVIEW_WEBHOOK_TOKEN not configured")
            return Response(
                {"error": "Webhook not configured"},
                status=status.HTTP_501_NOT_IMPLEMENTED,
            )

        try:
            verifier.verify_url_token(token, expected_token)
        except Exception as exc:
            logger.warning(
                "tradingview_webhook_invalid_token",
                extra={"error": str(exc)},
            )
            return Response(
                {"error": "Invalid token"},
                status=status.HTTP_401_UNAUTHORIZED,
            )

        if getattr(settings, "TRADINGVIEW_IP_WHITELIST_ENABLED", False):
            remote_addr = request.META.get("REMOTE_ADDR", "")
            try:
                verifier.verify_ip(remote_addr)
            except Exception as exc:
                logger.warning(
                    "tradingview_webhook_ip_blocked",
                    extra={"ip": remote_addr, "error": str(exc)},
                )
                return Response(
                    {"error": "Forbidden"},
                    status=status.HTTP_403_FORBIDDEN,
                )

        parser = TradingViewPayloadParser()
        try:
            payload = parser.parse(request.body)
        except Exception as exc:
            logger.warning(
                "tradingview_webhook_invalid_payload",
                extra={"error": str(exc)},
            )
            return Response(
                {"error": f"Invalid payload: {exc}"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        repo = RawWebhookEventRepository()
        raw_event = repo.create(
            source=WebhookSource.TRADINGVIEW.value,
            raw_body=payload,
            headers=dict(request.headers),
            signature_valid=True,
        )

        alert_id = payload.get("alert_id") or payload.get("id") or str(raw_event.id)
        correlation_source = f"{WebhookSource.TRADINGVIEW.value}:{alert_id}"

        event_bus = get_event_bus()
        event = DomainEvent.create(
            event_type="ingestion.RawAlertReceived",
            payload={
                "raw_payload": payload,
                "source": WebhookSource.TRADINGVIEW.value,
                "received_at": raw_event.received_at.isoformat(),
                "signature_valid": True,
            },
            correlation_id=uuid.UUID(
                hex=IdempotencyKey.generate(correlation_source).value[:32],
            ),
            version=1,
        )
        event_bus.publish(event)

        repo.mark_processed(raw_event.id)

        serializer = WebhookResponseSerializer({
            "status": "accepted",
            "event_id": raw_event.id,
        })
        return Response(serializer.data, status=status.HTTP_202_ACCEPTED)


class ChartinkWebhookView(GenericAPIView):
    """Receive Chartink scan result webhooks.

    POST /api/v1/ingestion/webhooks/chartink/{token}/

    The URL token must match ``settings.CHARTINK_WEBHOOK_TOKEN``.
    On successful signature verification, the payload is persisted as a
    ``RawWebhookEvent`` and an ``ingestion.ScanResultReceived`` event is
    published.

    Responses:
        ``202``: Webhook accepted.
        ``401``: Invalid token or signature.
        ``400``: Malformed payload.
    """

    permission_classes: list[Any] = []
    authentication_classes: list[Any] = []

    def post(self, request: Request, token: str) -> Response:
        verifier = WebhookSignatureVerifier(
            shared_secret=getattr(settings, "CHARTINK_SHARED_SECRET", None),
            allowed_ips=getattr(settings, "CHARTINK_ALLOWED_IPS", None),
        )

        expected_token = getattr(settings, "CHARTINK_WEBHOOK_TOKEN", "")
        if not expected_token:
            logger.error("CHARTINK_WEBHOOK_TOKEN not configured")
            return Response(
                {"error": "Webhook not configured"},
                status=status.HTTP_501_NOT_IMPLEMENTED,
            )

        try:
            verifier.verify_url_token(token, expected_token)
        except Exception as exc:
            logger.warning(
                "chartink_webhook_invalid_token",
                extra={"error": str(exc)},
            )
            return Response(
                {"error": "Invalid token"},
                status=status.HTTP_401_UNAUTHORIZED,
            )

        signature = request.META.get("HTTP_X_SIGNATURE", "")
        try:
            verifier.verify_header_signature(request.body, signature)
        except Exception as exc:
            logger.warning(
                "chartink_webhook_invalid_signature",
                extra={"error": str(exc)},
            )
            return Response(
                {"error": "Invalid signature"},
                status=status.HTTP_401_UNAUTHORIZED,
            )

        if getattr(settings, "CHARTINK_IP_WHITELIST_ENABLED", False):
            remote_addr = request.META.get("REMOTE_ADDR", "")
            try:
                verifier.verify_ip(remote_addr)
            except Exception as exc:
                logger.warning(
                    "chartink_webhook_ip_blocked",
                    extra={"ip": remote_addr, "error": str(exc)},
                )
                return Response(
                    {"error": "Forbidden"},
                    status=status.HTTP_403_FORBIDDEN,
                )

        try:
            payload = json.loads(request.body)
        except (json.JSONDecodeError, UnicodeDecodeError) as exc:
            return Response(
                {"error": f"Invalid JSON body: {exc}"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        repo = RawWebhookEventRepository()
        raw_event = repo.create(
            source=WebhookSource.CHARTINK.value,
            raw_body=payload,
            headers=dict(request.headers),
            signature_valid=True,
        )

        event_bus = get_event_bus()
        event = DomainEvent.create(
            event_type="ingestion.ScanResultReceived",
            payload={
                "scan_name": payload.get("scan_name", "chartink_scan"),
                "symbols": payload.get("symbols", []),
                "received_at": raw_event.received_at.isoformat(),
            },
            correlation_id=uuid.UUID(
                hex=IdempotencyKey.generate(
                    "chartink",
                    payload.get("scan_name", "unknown"),
                    raw_event.received_at.strftime("%Y-%m-%d-%H"),
                ).value[:32],
            ),
            version=1,
        )
        event_bus.publish(event)

        repo.mark_processed(raw_event.id)

        serializer = WebhookResponseSerializer({
            "status": "accepted",
            "event_id": raw_event.id,
        })
        return Response(serializer.data, status=status.HTTP_202_ACCEPTED)


class RawWebhookEventListView(ListAPIView):
    """Debug listing of ingested webhook events.

    GET /api/v1/ingestion/raw-events/

    Accessible only to staff users.

    Responses:
        ``200``: Paginated list of raw webhook events.
        ``401``: Authentication required.
        ``403``: Insufficient permissions.
    """

    serializer_class = RawWebhookEventSerializer
    permission_classes = [IsAuthenticated, IsStaffRole]

    def get_queryset(self):
        return RawWebhookEvent.objects.all().order_by("-received_at")
