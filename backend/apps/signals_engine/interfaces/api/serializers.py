from __future__ import annotations

from rest_framework import serializers

from apps.signals_engine.infrastructure.models import Signal


class SignalSerializer(serializers.ModelSerializer):
    class Meta:
        model = Signal
        fields = (
            "id",
            "account_id",
            "instrument_symbol",
            "timeframe",
            "direction",
            "confidence_hint",
            "indicator_snapshot",
            "source_alert_id",
            "created_at",
        )
        read_only_fields = (
            "id",
            "created_at",
        )
