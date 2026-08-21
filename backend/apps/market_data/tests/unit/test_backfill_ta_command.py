"""``backfill_ta`` management command tests.

Covers the CLI entrypoint that wraps ``CandleToTechnicalAnalysisBridge.backfill_ta_from_candles``:
symbol auto-discovery from candle rows, dry-run (report only, no writes), and
``--clean`` deleting existing ``TASnapshot`` rows for the target symbol before
backfilling. The bridge itself is stubbed so the test exercises command logic,
not the (already separately tested) TA ingestion pipeline.
"""

from __future__ import annotations

from datetime import timedelta
from io import StringIO

import pytest
from django.core.management import call_command
from django.utils import timezone as dj_timezone

from apps.market_data.infrastructure.models import Candle as CandleModel
from apps.market_data.infrastructure.models import Instrument as InstrumentModel
from apps.technical_analysis.infrastructure.models import TASnapshot as TASnapshotModel

pytestmark = pytest.mark.django_db


class FakeBridge:
    def __init__(self) -> None:
        self.calls: list[tuple] = []

    def backfill_ta_from_candles(
        self, instrument_token: int, timeframe: str, from_ts, to_ts
    ) -> int:
        self.calls.append((instrument_token, timeframe, from_ts, to_ts))
        return 2


@pytest.fixture
def instrument() -> InstrumentModel:
    return InstrumentModel.objects.create(
        instrument_token=9001,
        exchange="NSE",
        tradingsymbol="RELIANCE",
        name="Reliance Industries",
        is_active=True,
    )


def _seed_candles(instrument: InstrumentModel, n: int = 5) -> None:
    base = dj_timezone.now().replace(hour=10, minute=0, second=0, microsecond=0)
    for i in range(n):
        CandleModel.objects.create(
            instrument=instrument,
            timeframe="1D",
            timestamp=base - timedelta(days=n - i),
            open="100",
            high="101",
            low="99",
            close="100.5",
            volume=1000,
        )


@pytest.fixture(autouse=True)
def _patch_bridge(monkeypatch) -> FakeBridge:
    fake = FakeBridge()
    monkeypatch.setattr(
        "apps.market_data.management.commands.backfill_ta.CandleToTechnicalAnalysisBridge",
        lambda: fake,
    )
    return fake


class TestBackfillTaCommand:
    def test_dry_run_reports_without_writes(self, instrument) -> None:
        _seed_candles(instrument)
        out = StringIO()
        call_command("backfill_ta", timeframe="1D", dry_run=True, stdout=out)
        text = out.getvalue()
        assert "would backfill 5 candles" in text
        assert CandleModel.objects.count() == 5
        assert TASnapshotModel.objects.count() == 0

    def test_clean_removes_existing_snapshots_then_backfills(self, instrument) -> None:
        _seed_candles(instrument)
        TASnapshotModel.objects.create(
            symbol="RELIANCE",
            exchange="NSE",
            timeframe="1D",
            indicators={},
            raw_payload={},
            snapshot_timestamp=dj_timezone.now() - timedelta(days=1),
        )
        out = StringIO()
        call_command("backfill_ta", timeframe="1D", clean=True, stdout=out)
        text = out.getvalue()
        assert "removed 1 existing snapshots" in text
        assert TASnapshotModel.objects.count() == 0
        assert "backfilled 2 candles" in text

    def test_symbols_filter_limits_scope(self, instrument) -> None:
        _seed_candles(instrument)
        other = InstrumentModel.objects.create(
            instrument_token=9002,
            exchange="NSE",
            tradingsymbol="TCS",
            name="Tata Consultancy",
            is_active=True,
        )
        _seed_candles(other)
        out = StringIO()
        call_command("backfill_ta", symbols="RELIANCE", clean=True, stdout=out)
        text = out.getvalue()
        assert "RELIANCE" in text
        assert "TCS" not in text

    def test_no_candles_is_reported(self, instrument) -> None:
        out = StringIO()
        call_command("backfill_ta", symbols="RELIANCE", clean=True, stdout=out)
        text = out.getvalue()
        assert "no candles, skipping" in text