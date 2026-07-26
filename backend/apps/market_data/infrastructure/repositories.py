from __future__ import annotations

import logging
from datetime import datetime
from decimal import Decimal
from typing import Any

from django.db import models as db_models
from django.db.models import QuerySet

from apps.common.domain.value_objects import Symbol
from apps.market_data.domain.entities import Candle, Instrument
from apps.market_data.infrastructure.models import Candle as CandleModel
from apps.market_data.infrastructure.models import Instrument as InstrumentModel

logger = logging.getLogger(__name__)


class InstrumentRepository:
    """Repository for ``Instrument`` domain entities backed by the ORM model."""

    def find_by_symbol(self, symbol: Symbol) -> Instrument | None:
        """Look up an instrument by its ``Symbol`` value object."""
        try:
            obj = InstrumentModel.objects.get(
                exchange__iexact=symbol.exchange,
                tradingsymbol__iexact=symbol.tradingsymbol,
            )
            return self._to_domain(obj)
        except InstrumentModel.DoesNotExist:
            return None

    def find_by_token(self, instrument_token: int) -> Instrument | None:
        """Look up an instrument by its exchange token."""
        try:
            obj = InstrumentModel.objects.get(pk=instrument_token)
            return self._to_domain(obj)
        except InstrumentModel.DoesNotExist:
            return None

    def search(
        self,
        query: str,
        exchange: str | None = None,
        limit: int = 20,
    ) -> list[Instrument]:
        """Search instruments by symbol or name (case-insensitive prefix)."""
        qs: QuerySet[InstrumentModel] = InstrumentModel.objects.filter(
            is_active=True,
        )
        if exchange:
            qs = qs.filter(exchange__iexact=exchange)

        qs = qs.filter(
            db_models.Q(tradingsymbol__icontains=query)
            | db_models.Q(name__icontains=query)
        )[:limit]

        return [self._to_domain(obj) for obj in qs]

    def save(self, instrument: Instrument) -> Instrument:
        """Persist a new instrument or update an existing one."""
        obj, _ = InstrumentModel.objects.update_or_create(
            instrument_token=instrument.instrument_token,
            defaults={
                "exchange": instrument.exchange,
                "tradingsymbol": instrument.tradingsymbol,
                "name": instrument.name,
                "segment": instrument.segment,
                "lot_size": instrument.lot_size,
                "tick_size": instrument.tick_size,
                "instrument_type": instrument.instrument_type,
                "expiry": instrument.expiry,
                "is_active": instrument.is_active,
            },
        )
        return self._to_domain(obj)

    def update_from_dict(self, instrument_token: int, data: dict[str, Any]) -> None:
        """Update instrument fields from a dictionary."""
        allowed_fields = {
            "tradingsymbol", "name", "segment", "lot_size",
            "tick_size", "instrument_type", "expiry", "is_active",
            "exchange",
        }
        filtered = {k: v for k, v in data.items() if k in allowed_fields and v is not None}
        if filtered:
            InstrumentModel.objects.filter(pk=instrument_token).update(**filtered)

    def deactivate_missing(self, active_tokens: set[int]) -> int:
        """Set ``is_active=False`` for instruments not in *active_tokens*."""
        return InstrumentModel.objects.filter(is_active=True).exclude(
            pk__in=active_tokens,
        ).update(is_active=False)

    @staticmethod
    def _to_domain(obj: InstrumentModel) -> Instrument:
        return Instrument(
            instrument_token=obj.instrument_token,
            exchange=obj.exchange,
            tradingsymbol=obj.tradingsymbol,
            name=obj.name,
            segment=obj.segment,
            lot_size=obj.lot_size,
            tick_size=obj.tick_size,
            instrument_type=obj.instrument_type,
            expiry=obj.expiry,
            is_active=obj.is_active,
        )


class CandleRepository:
    """Repository for ``Candle`` domain entities backed by the ORM model."""

    def find_latest(
        self,
        instrument_token: int,
        timeframe: str,
        limit: int = 100,
    ) -> list[Candle]:
        """Return the most recent *limit* candles for the given instrument/timeframe."""
        qs: QuerySet[CandleModel] = (
            CandleModel.objects.filter(
                instrument_id=instrument_token,
                timeframe=timeframe,
            )
            .order_by("-timestamp")[:limit]
        )
        candles = [self._to_domain(c) for c in qs]
        candles.reverse()
        return candles

    def find_range(
        self,
        instrument_token: int,
        timeframe: str,
        from_timestamp: datetime,
        to_timestamp: datetime,
    ) -> list[Candle]:
        """Return candles for the given time range (chronological)."""
        qs: QuerySet[CandleModel] = (
            CandleModel.objects.filter(
                instrument_id=instrument_token,
                timeframe=timeframe,
                timestamp__gte=from_timestamp,
                timestamp__lte=to_timestamp,
            )
            .order_by("timestamp")
        )
        return [self._to_domain(c) for c in qs]

    def upsert(
        self,
        instrument_token: int,
        timeframe: str,
        timestamp: datetime,
        open: Decimal,
        high: Decimal,
        low: Decimal,
        close: Decimal,
        volume: int,
    ) -> None:
        """Insert or update a single candle row."""
        CandleModel.objects.update_or_create(
            instrument_id=instrument_token,
            timeframe=timeframe,
            timestamp=timestamp,
            defaults={
                "open": open,
                "high": high,
                "low": low,
                "close": close,
                "volume": volume,
            },
        )

    def bulk_upsert(self, candles: list[Candle]) -> int:
        """Efficiently bulk upsert a list of candles.

        Returns the number of rows affected.
        """
        objs: list[CandleModel] = []
        for c in candles:
            objs.append(CandleModel(
                instrument_id=c.instrument_token,
                timeframe=c.timeframe,
                timestamp=c.timestamp,
                open=c.open,
                high=c.high,
                low=c.low,
                close=c.close,
                volume=c.volume,
            ))

        if not objs:
            return 0

        CandleModel.objects.bulk_create(
            objs,
            update_conflicts=True,
            update_fields=["open", "high", "low", "close", "volume"],
            unique_fields=["instrument_id", "timeframe", "timestamp"],
        )
        return len(objs)

    @staticmethod
    def _to_domain(obj: CandleModel) -> Candle:
        return Candle(
            instrument_token=obj.instrument_id,
            timeframe=obj.timeframe,
            timestamp=obj.timestamp,
            open=obj.open,
            high=obj.high,
            low=obj.low,
            close=obj.close,
            volume=obj.volume,
        )



