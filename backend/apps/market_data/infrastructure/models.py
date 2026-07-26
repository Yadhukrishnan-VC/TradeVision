from __future__ import annotations

from decimal import Decimal

from django.db import models

from apps.common.infrastructure.model_mixins import TimestampedModel


class Instrument(TimestampedModel):
    """Persistent ORM model for tradeable financial instruments.

    This is the database representation of the ``Instrument`` domain entity.
    The domain entity in ``domain.entities`` is used for inter-layer data
    transfer; this model handles persistence and querying.

    Indexes:
        - ``(exchange, tradingsymbol)``: unique together, used for symbol lookups.
        - ``is_active``: filtered queries for active-only instruments.
    """

    instrument_token = models.BigIntegerField(
        primary_key=True,
        help_text="Exchange-assigned numeric token.",
    )
    exchange = models.CharField(
        max_length=10,
        db_index=True,
        help_text="Exchange code (e.g. NSE, BSE).",
    )
    tradingsymbol = models.CharField(
        max_length=100,
        help_text="Exchange-listed trading symbol (e.g. RELIANCE).",
    )
    name = models.CharField(
        max_length=255,
        blank=True,
        default="",
        help_text="Human-readable company name.",
    )
    segment = models.CharField(
        max_length=50,
        blank=True,
        default="",
        help_text="Market segment (e.g. EQUITY, FNO).",
    )
    lot_size = models.IntegerField(
        default=1,
        help_text="Minimum trade quantity.",
    )
    tick_size = models.DecimalField(
        max_digits=20,
        decimal_places=4,
        default=Decimal("0.05"),
        help_text="Minimum price increment.",
    )
    instrument_type = models.CharField(
        max_length=20,
        blank=True,
        default="",
        help_text="Instrument category (e.g. EQ, FUT, OPT).",
    )
    expiry = models.DateTimeField(
        null=True,
        blank=True,
        help_text="Derivative contract expiry (UTC).",
    )
    is_active = models.BooleanField(
        default=True,
        db_index=True,
        help_text="Whether this instrument is currently tradeable.",
    )

    class Meta:
        app_label = "market_data"
        db_table = "market_data_instrument"
        verbose_name = "Instrument"
        verbose_name_plural = "Instruments"
        unique_together = [("exchange", "tradingsymbol")]
        indexes = [
            models.Index(fields=["exchange", "tradingsymbol"], name="idx_instrument_exchange_symbol"),
            models.Index(fields=["is_active"], name="idx_instrument_active"),
        ]

    def __str__(self) -> str:
        return f"{self.exchange}:{self.tradingsymbol}"


class Candle(TimestampedModel):
    """Persistent ORM model for aggregated OHLCV candles.

    Each row represents one aggregated candle for a specific instrument,
    timeframe, and timestamp. The combination is unique so the same candle
    can be safely upserted.

    Indexes:
        - ``(instrument, timeframe, timestamp)``: unique together,
          the primary access pattern for candle queries.
    """

    id = models.BigAutoField(primary_key=True)
    instrument = models.ForeignKey(
        Instrument,
        on_delete=models.CASCADE,
        related_name="candles",
        help_text="The instrument this candle belongs to.",
    )
    timeframe = models.CharField(
        max_length=10,
        db_index=True,
        help_text="Aggregation interval (e.g. 1min, 15min, 1D).",
    )
    timestamp = models.DateTimeField(
        db_index=True,
        help_text="Candle open time (UTC).",
    )
    open = models.DecimalField(
        max_digits=20,
        decimal_places=4,
        help_text="Opening price.",
    )
    high = models.DecimalField(
        max_digits=20,
        decimal_places=4,
        help_text="Highest price during the interval.",
    )
    low = models.DecimalField(
        max_digits=20,
        decimal_places=4,
        help_text="Lowest price during the interval.",
    )
    close = models.DecimalField(
        max_digits=20,
        decimal_places=4,
        help_text="Closing price.",
    )
    volume = models.BigIntegerField(
        help_text="Total traded volume.",
    )

    class Meta:
        app_label = "market_data"
        db_table = "market_data_candle"
        verbose_name = "Candle"
        verbose_name_plural = "Candles"
        unique_together = [("instrument", "timeframe", "timestamp")]
        indexes = [
            models.Index(
                fields=["instrument", "timeframe", "-timestamp"],
                name="idx_candle_lookup",
            ),
        ]

    def __str__(self) -> str:
        return f"Candle({self.instrument_id}, {self.timeframe}, {self.timestamp})"
