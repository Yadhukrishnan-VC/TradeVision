"""backfill_historical management command tests.

Covers the CLI entrypoint that wraps ``HistoricalSyncService``: symbol→token
resolution, dry-run (fetch + report, no writes) and real run (persists through
the service), plus failure output. Uses the ``paper`` provider so no external
network is involved.
"""

from __future__ import annotations

from datetime import timezone
from io import StringIO

import pytest
from django.core.management import call_command
from django.core.management.base import CommandError

from apps.market_data.infrastructure.models import Candle as CandleModel
from apps.market_data.infrastructure.models import Instrument as InstrumentModel

pytestmark = pytest.mark.django_db

_UTC = timezone.utc


@pytest.fixture
def instrument() -> InstrumentModel:
    return InstrumentModel.objects.create(
        instrument_token=12345,
        exchange="NSE",
        tradingsymbol="RELIANCE",
        name="Reliance Industries",
        is_active=True,
    )


class TestBackfillHistoricalCommand:
    def test_dry_run_fetches_and_persists_nothing(self, instrument) -> None:
        out = StringIO()
        call_command(
            "backfill_historical",
            provider="paper",
            symbols="RELIANCE",
            timeframe="1D",
            days=2,
            dry_run=True,
            stdout=out,
        )
        text = out.getvalue()
        assert "mode=dry-run" in text
        assert "bars would be persisted" in text
        assert CandleModel.objects.count() == 0

    def test_real_run_persists_via_service(self, instrument) -> None:
        out = StringIO()
        call_command(
            "backfill_historical",
            provider="paper",
            symbols="NSE:RELIANCE",
            timeframe="1D",
            from_ts="2026-08-14T00:00:00+00:00",
            to_ts="2026-08-19T00:00:00+00:00",
            stdout=out,
        )
        text = out.getvalue()
        assert "candles persisted" in text
        assert "failures=0" in text
        assert (
            CandleModel.objects.filter(
                instrument_id=instrument.instrument_token
            ).count()
            >= 1
        )

    def test_unknown_symbol_is_failure_output(self) -> None:
        out = StringIO()
        err = StringIO()
        with pytest.raises(CommandError):
            call_command(
                "backfill_historical",
                provider="paper",
                symbols="NOTAREALSYMBOL",
                timeframe="1D",
                days=1,
                stdout=out,
                stderr=err,
            )
        assert "not found, skipping" in err.getvalue()

    def test_requires_from_or_days(self, instrument) -> None:
        out = StringIO()
        with pytest.raises(CommandError, match="exactly one of --from or --days"):
            call_command(
                "backfill_historical",
                provider="paper",
                symbols="RELIANCE",
                timeframe="1D",
                stdout=out,
            )
