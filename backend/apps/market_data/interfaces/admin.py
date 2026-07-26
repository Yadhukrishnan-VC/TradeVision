from __future__ import annotations

from django.contrib import admin

from apps.market_data.infrastructure.models import Candle, Instrument


@admin.register(Instrument)
class InstrumentAdmin(admin.ModelAdmin):
    """Admin interface for the ``Instrument`` model."""

    list_display = [
        "instrument_token",
        "exchange",
        "tradingsymbol",
        "name",
        "segment",
        "instrument_type",
        "is_active",
    ]
    list_filter = ["exchange", "segment", "instrument_type", "is_active"]
    search_fields = ["tradingsymbol", "name", "exchange"]
    ordering = ["exchange", "tradingsymbol"]


@admin.register(Candle)
class CandleAdmin(admin.ModelAdmin):
    """Admin interface for the ``Candle`` model."""

    list_display = [
        "instrument",
        "timeframe",
        "timestamp",
        "open",
        "high",
        "low",
        "close",
        "volume",
    ]
    list_filter = ["timeframe", "instrument__exchange"]
    search_fields = ["instrument__tradingsymbol"]
    date_hierarchy = "timestamp"
    ordering = ["-timestamp"]
