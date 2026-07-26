from __future__ import annotations

from rest_framework import serializers

from apps.ingestion.infrastructure.models import RawWebhookEvent


class TradingViewWebhookSerializer(serializers.Serializer):
    """Validator for incoming TradingView webhook payloads.

    Accepts any JSON payload; the actual parsing is handled by
    ``TradingViewPayloadParser`` in the application layer.
    """

    pass


class ChartinkWebhookSerializer(serializers.Serializer):
    """Validator for incoming Chartink webhook payloads."""

    pass


class RawWebhookEventSerializer(serializers.ModelSerializer):
    """Serializer for the ``RawWebhookEvent`` model.

    Used by the debug listing endpoint.
    """

    class Meta:
        model = RawWebhookEvent
        fields = [
            "id",
            "source",
            "signature_valid",
            "received_at",
            "processed",
        ]
        read_only_fields = fields


class WebhookResponseSerializer(serializers.Serializer):
    """Standard response for accepted webhook requests."""

    status = serializers.CharField(default="accepted")
    event_id = serializers.UUIDField(required=False)
