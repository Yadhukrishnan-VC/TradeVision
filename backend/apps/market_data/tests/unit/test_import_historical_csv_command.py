"""REAL-DATA-BACKFILL-2 fix #4 — import_historical_csv command tests.

Covers CSV parsing/validation, the bulk_upsert write path (idempotency:
re-running does not duplicate candles), SyncRun audit rows, and the
synthetic-token instrument creation for symbols not yet in the DB.
"""

from __future__ import annotations

import csv
from datetime import datetime, timezone
from io import StringIO
from pathlib import Path

import pytest
from django.core.management import call_command

from apps.market_data.infrastructure.models import Candle as CandleModel
from apps.market_data.infrastructure.models import Instrument as InstrumentModel
from apps.market_data.infrastructure.models import SyncRun

pytestmark = pytest.mark.django_db

_UTC = timezone.utc

_HEADERS = ["date", "open", "high", "low", "close", "volume", "symbol"]


def _write_csv(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=_HEADERS)
        writer.writeheader()
        writer.writerows(rows)


def _make_rows(symbol: str, start_day: int = 1, count: int = 3) -> list[dict]:
    return [
        {
            "date": f"2026-08-{start_day + i:02d}",
            "open": "100.00",
            "high": "101.00",
            "low": "99.00",
            "close": "100.50",
            "volume": "1000",
            "symbol": symbol,
        }
        for i in range(count)
    ]


class TestImportHistoricalCsv:
    def test_import_creates_instruments_candles_and_syncruns(self, tmp_path: Path) -> None:
        _write_csv(tmp_path / "RELIANCE.csv", _make_rows("RELIANCE"))

        out = StringIO()
        call_command(
            "import_historical_csv",
            csv_dir=str(tmp_path),
            timeframe="1D",
            exchange="NSE",
            stdout=out,
        )

        inst = InstrumentModel.objects.get(exchange="NSE", tradingsymbol="RELIANCE")
        assert CandleModel.objects.filter(instrument_id=inst.instrument_token).count() == 3
        assert SyncRun.objects.filter(symbol="RELIANCE", status="COMPLETED").count() == 1
        run = SyncRun.objects.get(symbol="RELIANCE")
        assert run.rows_written == 3
        assert run.source == "csv"
        assert run.finished_at is not None

    def test_reimport_is_idempotent(self, tmp_path: Path) -> None:
        _write_csv(tmp_path / "RELIANCE.csv", _make_rows("RELIANCE"))

        out1 = StringIO()
        call_command(
            "import_historical_csv",
            csv_dir=str(tmp_path),
            timeframe="1D",
            stdout=out1,
        )
        out2 = StringIO()
        call_command(
            "import_historical_csv",
            csv_dir=str(tmp_path),
            timeframe="1D",
            stdout=out2,
        )

        inst = InstrumentModel.objects.get(exchange="NSE", tradingsymbol="RELIANCE")
        assert CandleModel.objects.filter(instrument_id=inst.instrument_token).count() == 3

    def test_invalid_rows_are_skipped(self, tmp_path: Path) -> None:
        rows = _make_rows("RELIANCE")
        rows.append({"date": "not-a-date", "open": "x", "high": "y", "low": "z", "close": "w", "volume": "z", "symbol": "RELIANCE"})
        _write_csv(tmp_path / "RELIANCE.csv", rows)

        out = StringIO()
        call_command(
            "import_historical_csv",
            csv_dir=str(tmp_path),
            timeframe="1D",
            stdout=out,
        )

        inst = InstrumentModel.objects.get(exchange="NSE", tradingsymbol="RELIANCE")
        assert CandleModel.objects.filter(instrument_id=inst.instrument_token).count() == 3

    def test_missing_required_column_is_reported(self, tmp_path: Path) -> None:
        path = tmp_path / "RELIANCE.csv"
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("w", encoding="utf-8", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=["date", "open", "close"])
            writer.writeheader()
            writer.writerow({"date": "2026-08-01", "open": "100", "close": "101"})

        out = StringIO()
        with pytest.raises(SystemExit) as exc:
            call_command(
                "import_historical_csv",
                csv_dir=str(tmp_path),
                timeframe="1D",
                stdout=out,
            )
        assert exc.value.code == 1

    def test_dry_run_parses_without_persisting(self, tmp_path: Path) -> None:
        _write_csv(tmp_path / "RELIANCE.csv", _make_rows("RELIANCE"))

        out = StringIO()
        call_command(
            "import_historical_csv",
            csv_dir=str(tmp_path),
            timeframe="1D",
            dry_run=True,
            stdout=out,
        )

        assert CandleModel.objects.count() == 0
        assert SyncRun.objects.filter(symbol="RELIANCE").count() == 1
        assert "dry_run=True" in out.getvalue()

    def test_symbols_filter(self, tmp_path: Path) -> None:
        _write_csv(tmp_path / "RELIANCE.csv", _make_rows("RELIANCE"))
        _write_csv(tmp_path / "TCS.csv", _make_rows("TCS"))

        out = StringIO()
        call_command(
            "import_historical_csv",
            csv_dir=str(tmp_path),
            timeframe="1D",
            symbols="TCS",
            stdout=out,
        )

        assert InstrumentModel.objects.filter(tradingsymbol="TCS").exists()
        assert not InstrumentModel.objects.filter(tradingsymbol="RELIANCE").exists()