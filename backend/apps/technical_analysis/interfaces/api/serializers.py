from __future__ import annotations

from rest_framework import serializers

from apps.technical_analysis.infrastructure.models import TASnapshot


class TradingViewTechnicalAnalysisSerializer(serializers.Serializer):
    """Pass-through validator for incoming TradingView TA webhook payloads.

    Structural validation is delegated to the application service layer.
    The serializer exists to maintain Clean Architecture boundaries —
    the view layer uses a serializer class for shape definition even when
    validation is minimal.
    """

    pass


class TASnapshotSerializer(serializers.ModelSerializer):
    """Serializer for the ``TASnapshot`` model.

    Used by admin and debug endpoints.
    """

    indicator_count = serializers.SerializerMethodField()

    class Meta:
        model = TASnapshot
        fields = [
            "id",
            "symbol",
            "exchange",
            "timeframe",
            "pine_id",
            "pine_version",
            "indicator_count",
            "snapshot_timestamp",
            "received_at",
        ]
        read_only_fields = [
            "id",
            "symbol",
            "exchange",
            "timeframe",
            "pine_id",
            "pine_version",
            "indicator_count",
            "snapshot_timestamp",
            "received_at",
        ]

    @staticmethod
    def get_indicator_count(obj: TASnapshot) -> int:
        return len(obj.indicators)


class TechnicalAnalysisResponseSerializer(serializers.Serializer):
    """Standard response for accepted technical analysis webhook requests."""

    status = serializers.CharField(default="accepted")
    snapshot_id = serializers.UUIDField(required=False)
