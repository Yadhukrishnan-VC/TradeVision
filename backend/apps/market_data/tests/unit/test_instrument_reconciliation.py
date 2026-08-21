"""REAL-DATA-BACKFILL-2 fix #1 — instrument identity reconciliation.

Proves that ``InstrumentSyncService.sync()`` matches upstream instruments by
``(exchange, tradingsymbol)`` BEFORE falling back to token-only matching, so an
instrument created with a *synthetic* token by ``import_historical_csv`` gets
its token replaced in place by the real provider token — and its candle history
survives the merge (no duplicate row, no orphaned candles).
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest
from django.conf import settings

from apps.market_data.application.instrument_sync_service import (
    InstrumentSyncService,
)
from apps.market_data.infrastructure.models import Candle as CandleModel
from apps.market_data.infrastructure.models import Instrument as InstrumentModel
from apps.market_data.infrastructure.repositories import InstrumentRepository
from core.market_data.provider_factory import MarketDataProviderFactory

pytestmark = pytest.mark.django_db

_UTC = timezone.utc


@pytest.fixture(autouse=True)
def _use_paper_provider(settings) -> None:
    """InstrumentSyncService needs a provider that implements fetch_instruments()."""
    settings.MARKET_DATA_PROVIDER = "paper"
    MarketDataProviderFactory.reset()
    yield
    MarketDataProviderFactory.reset()


def _make_synthetic_token(exchange: str, tradingsymbol: str) -> int:
    import hashlib

    return int(hashlib.md5(f"{exchange}:{tradingsymbol}".encode()).hexdigest()[:15], 16)


def _create_candle(instrument_token: int, day_offset: int) -> CandleModel:
    return CandleModel.objects.create(
        instrument_id=instrument_token,
        timeframe="1D",
        timestamp=datetime(2026, 8, 1, tzinfo=_UTC) - timedelta(days=day_offset),
        open=Decimal("1000.00"),
        high=Decimal("1010.00"),
        low=Decimal("990.00"),
        close=Decimal("1005.00"),
        volume=1_000_000,
    )


class TestInstrumentTokenReconciliation:
    def test_sync_replaces_synthetic_token_in_place_preserving_candles(self) -> None:
        synth_token = _make_synthetic_token("NSE", "RELIANCE")
        instrument = InstrumentModel.objects.create(
            instrument_token=synth_token,
            exchange="NSE",
            tradingsymbol="RELIANCE",
            name="Reliance Industries Ltd",
            segment="EQUITY",
            lot_size=1,
            tick_size=Decimal("0.05"),
            instrument_type="EQ",
            is_active=True,
        )
        c1 = _create_candle(synth_token, 0)
        c2 = _create_candle(synth_token, 1)

        result = InstrumentSyncService().sync()

        # Paper provider assigns RELIANCE the token 1000.
        assert result["merged"] == 1
        assert not InstrumentModel.objects.filter(pk=synth_token).exists()

        reconciled = InstrumentModel.objects.get(
            exchange="NSE", tradingsymbol="RELIANCE"
        )
        assert reconciled.instrument_token == 1000

        # Candle history survived, still attached to the instrument.
        candle_ts = {c.timestamp for c in CandleModel.objects.filter(instrument_id=1000)}
        assert {c1.timestamp, c2.timestamp} == candle_ts
        # No orphaned candles on the old token.
        assert not CandleModel.objects.filter(instrument_id=synth_token).exists()

    def test_sync_does_not_duplicate_when_symbol_and_token_both_match(self) -> None:
        InstrumentModel.objects.create(
            instrument_token=1000,
            exchange="NSE",
            tradingsymbol="RELIANCE",
            name="Reliance Industries Ltd",
            segment="EQUITY",
            lot_size=1,
            tick_size=Decimal("0.05"),
            instrument_type="EQ",
            is_active=True,
        )
        result = InstrumentSyncService().sync()

        assert result["created"] == 9  # paper provider exposes 10 symbols total
        assert result["merged"] == 0
        assert InstrumentModel.objects.filter(
            exchange="NSE", tradingsymbol="RELIANCE"
        ).count() == 1

    def test_sync_symbol_match_takes_precedence_over_token_match(self) -> None:
        """A symbol that differs only by token must be merged, never duplicated."""
        synth_token = _make_synthetic_token("NSE", "TCS")
        InstrumentModel.objects.create(
            instrument_token=synth_token,
            exchange="NSE",
            tradingsymbol="TCS",
            name="Tata Consultancy Services Ltd",
            segment="EQUITY",
            lot_size=1,
            tick_size=Decimal("0.05"),
            instrument_type="EQ",
            is_active=True,
        )
        _create_candle(synth_token, 0)

        result = InstrumentSyncService().sync()

        assert result["merged"] == 1
        assert InstrumentModel.objects.filter(
            exchange="NSE", tradingsymbol="TCS"
        ).count() == 1
        assert InstrumentModel.objects.get(
            exchange="NSE", tradingsymbol="TCS"
        ).instrument_token == 1001  # TCS is the 2nd entry in the paper master
        assert CandleModel.objects.filter(instrument_id=1001).count() == 1

    def test_fields_updated_after_token_reconciliation(self) -> None:
        synth_token = _make_synthetic_token("NSE", "INFY")
        InstrumentModel.objects.create(
            instrument_token=synth_token,
            exchange="NSE",
            tradingsymbol="INFY",
            name="Wrong Name",
            segment="EQUITY",
            lot_size=1,
            tick_size=Decimal("0.05"),
            instrument_type="EQ",
            is_active=True,
        )
        result = InstrumentSyncService().sync()

        assert result["merged"] == 1
        infy = InstrumentModel.objects.get(exchange="NSE", tradingsymbol="INFY")
        assert infy.instrument_token == 1002  # INFY is the 3rd entry
        assert infy.name == "Infosys Ltd"
        assert infy.lot_size == 1


class TestSyncRunAudit:
    def test_syncrun_created_fields(self) -> None:
        from apps.market_data.infrastructure.models import SyncRun

        run = SyncRun.objects.create(
            source=SyncRun.Source.CSV,
            symbol="RELIANCE",
            timeframe="1D",
            range_start=datetime(2026, 8, 1, tzinfo=_UTC),
            range_end=datetime(2026, 8, 19, tzinfo=_UTC),
            rows_written=762,
            status=SyncRun.Status.COMPLETED,
        )
        assert run.pk is not None
        assert run.source == "csv"
        assert run.status == "COMPLETED"
        assert run.rows_written == 762
        assert run.finished_at is None

    def test_syncrun_status_transition(self) -> None:
        from apps.market_data.infrastructure.models import SyncRun
        from django.utils import timezone as dj_timezone

        run = SyncRun.objects.create(
            source=SyncRun.Source.ZERODHA,
            symbol="INSTRUMENT_MASTER",
            timeframe="N/A",
            range_start=datetime.min.replace(tzinfo=_UTC),
            range_end=datetime.max.replace(tzinfo=_UTC),
            status=SyncRun.Status.RUNNING,
        )
        run.status = SyncRun.Status.FAILED
        run.error_message = "boom"
        run.finished_at = dj_timezone.now()
        run.save()
        run.refresh_from_db()
        assert run.status == "FAILED"
        assert run.error_message == "boom"


class TestCandleBulkUpsertIdempotency:
    def test_re_upsert_does_not_duplicate_candles(self) -> None:
        from apps.market_data.domain.entities import Candle
        from apps.market_data.infrastructure.repositories import CandleRepository

        inst = InstrumentModel.objects.create(
            instrument_token=9000,
            exchange="NSE",
            tradingsymbol="TESTBULK",
            name="Test",
            segment="EQUITY",
            lot_size=1,
            tick_size=Decimal("0.05"),
            instrument_type="EQ",
            is_active=True,
        )
        repo = CandleRepository()
        ts = datetime(2026, 8, 1, tzinfo=_UTC)
        candles = [
            Candle(
                instrument_token=inst.instrument_token,
                timeframe="1D",
                timestamp=ts + timedelta(days=i),
                open=Decimal("10.00"),
                high=Decimal("11.00"),
                low=Decimal("9.00"),
                close=Decimal("10.50"),
                volume=100,
            )
            for i in range(5)
        ]

        first = repo.bulk_upsert(candles)
        assert first == 5
        assert CandleModel.objects.filter(instrument_id=inst.instrument_token).count() == 5

        # Re-running the exact same candles must not create new rows.
        second = repo.bulk_upsert(candles)
        assert second == 5
        assert CandleModel.objects.filter(instrument_id=inst.instrument_token).count() == 5

        # Overlapping partial re-run still no growth.
        repo.bulk_upsert(candles[:3])
        assert CandleModel.objects.filter(instrument_id=inst.instrument_token).count() == 5