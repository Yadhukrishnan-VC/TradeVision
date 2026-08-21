"""REAL-DATA-BACKFILL-2 fix #4 — sync_instrument_master command tests.

Covers the command's dry-run path, the SyncRun audit record it creates, and
the full sync path that replaces synthetic tokens with real provider tokens
(via ``InstrumentSyncService``, whose merge logic is tested separately).
"""

from __future__ import annotations

import hashlib
from datetime import datetime, timezone
from decimal import Decimal
from io import StringIO

import pytest
from django.conf import settings
from django.core.management import call_command

from apps.market_data.infrastructure.models import Instrument as InstrumentModel
from apps.market_data.infrastructure.models import SyncRun
from core.market_data.provider_factory import MarketDataProviderFactory

pytestmark = pytest.mark.django_db

_UTC = timezone.utc


@pytest.fixture(autouse=True)
def _use_paper_provider(settings) -> None:
    settings.MARKET_DATA_PROVIDER = "paper"
    MarketDataProviderFactory.reset()
    yield
    MarketDataProviderFactory.reset()


def _synthetic_token(symbol: str) -> int:
    return int(hashlib.md5(f"NSE:{symbol}".encode()).hexdigest()[:15], 16)


class TestSyncInstrumentMasterCommand:
    def test_dry_run_reports_without_persisting(self) -> None:
        out = StringIO()
        call_command(
            "sync_instrument_master",
            provider="paper",
            symbols="RELIANCE,TCS",
            segment="EQUITY",
            exchange="NSE",
            dry_run=True,
            stdout=out,
        )
        text = out.getvalue()
        assert "Fetched 10 instruments from master" in text
        assert "Would create: 2" in text
        # dry-run does not persist instruments
        assert InstrumentModel.objects.count() == 0
        # but does leave an audit trail
        assert SyncRun.objects.filter(symbol="INSTRUMENT_MASTER", status="COMPLETED").count() == 1

    def test_full_sync_creates_instruments(self) -> None:
        out = StringIO()
        call_command(
            "sync_instrument_master",
            provider="paper",
            segment="EQUITY",
            exchange="NSE",
            stdout=out,
        )
        assert InstrumentModel.objects.count() == 10
        assert InstrumentModel.objects.filter(tradingsymbol="RELIANCE", instrument_token=1000).exists()
        run = SyncRun.objects.get(symbol="INSTRUMENT_MASTER", status="COMPLETED")
        assert run.rows_written == 10

    def test_sync_reconciles_synthetic_token_in_place(self) -> None:
        synth = _synthetic_token("RELIANCE")
        InstrumentModel.objects.create(
            instrument_token=synth,
            exchange="NSE",
            tradingsymbol="RELIANCE",
            name="Reliance Industries Ltd",
            segment="EQUITY",
            lot_size=1,
            tick_size=Decimal("0.05"),
            instrument_type="EQ",
            is_active=True,
        )
        out = StringIO()
        call_command(
            "sync_instrument_master",
            provider="paper",
            symbols="RELIANCE",
            segment="EQUITY",
            exchange="NSE",
            stdout=out,
        )
        assert not InstrumentModel.objects.filter(pk=synth).exists()
        row = InstrumentModel.objects.get(exchange="NSE", tradingsymbol="RELIANCE")
        assert row.instrument_token == 1000

    def test_provider_without_fetch_instruments_is_reported(self) -> None:
        from django.core.management.base import CommandError

        out = StringIO()
        err = StringIO()
        with pytest.raises(SystemExit) as exc:
            call_command(
                "sync_instrument_master",
                provider="mock",
                dry_run=True,
                stdout=out,
                stderr=err,
            )
        assert exc.value.code == 1
        assert SyncRun.objects.filter(status="FAILED").count() == 1