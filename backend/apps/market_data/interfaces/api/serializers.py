from __future__ import annotations

from rest_framework import serializers

from apps.market_data.domain.value_objects import Timeframe
from apps.market_data.infrastructure.models import Candle, Instrument


class InstrumentSerializer(serializers.ModelSerializer):
    """Serializer for the ``Instrument`` model.

    Used by ``InstrumentSearchView`` to return paginated instrument
    search results.
    """

    class Meta:
        model = Instrument
        fields = [
            "instrument_token",
            "exchange",
            "tradingsymbol",
            "name",
            "segment",
            "lot_size",
            "tick_size",
            "instrument_type",
            "expiry",
            "is_active",
        ]
        read_only_fields = fields


class CandleSerializer(serializers.Serializer):
    """Serializer for candle data returned by ``CandleListView``.

    This is a read-only serializer that maps the ``Candle`` domain entity
    fields to the API response. It does not correspond to a single model
    since candles may come from cache or the database.
    """

    instrument_token = serializers.IntegerField()
    timeframe = serializers.CharField()
    timestamp = serializers.DateTimeField()
    open = serializers.DecimalField(max_digits=20, decimal_places=4)
    high = serializers.DecimalField(max_digits=20, decimal_places=4)
    low = serializers.DecimalField(max_digits=20, decimal_places=4)
    close = serializers.DecimalField(max_digits=20, decimal_places=4)
    volume = serializers.IntegerField()


class SessionStatusSerializer(serializers.Serializer):
    """Serializer for the market session status response."""

    status = serializers.CharField()


class CandleQuerySerializer(serializers.Serializer):
    """Validator for candle query parameters."""

    timeframe = serializers.ChoiceField(
        choices=[tf.value for tf in Timeframe],
        default="15min",
    )
    lookback = serializers.IntegerField(
        min_value=1,
        max_value=500,
        default=50,
    )


class InstrumentQuerySerializer(serializers.Serializer):
    """Validator for instrument search query parameters."""

    q = serializers.CharField(
        required=False,
        default="",
        allow_blank=True,
    )
    exchange = serializers.ChoiceField(
        choices=["NSE", "BSE"],
        required=False,
    )
