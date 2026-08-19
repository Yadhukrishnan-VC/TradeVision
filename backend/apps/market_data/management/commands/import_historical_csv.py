"""
Management command: import_historical_csv

Import historical OHLCV data from CSV files into the Candle table using the
existing HistoricalSyncService write path (CandleRepository.bulk_upsert).

CSV files must have columns: date, open, high, low, close, volume, symbol
where symbol is the bare NSE trading symbol (e.g., RELIANCE).

Each CSV file represents one symbol. The command creates SyncRun audit records
for each import operation.

Usage::

    python manage.py import_historical_csv \\
        --csv-dir data/nifty50_daily \\
        --timeframe 1D \\
        --exchange NSE

    python manage.py import_historical_csv \\
        --csv-dir data/nifty50_daily \\
        --symbols RELIANCE,TCS,INFY \\
        --timeframe 1D
"""

from __future__ import annotations

import csv
import sys
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from typing import Any

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone as dj_timezone

from apps.common.domain.value_objects import Symbol
from apps.market_data.application.historical_sync_service import get_historical_sync_service
from apps.market_data.domain.value_objects import Timeframe
from apps.market_data.infrastructure.models import Candle as CandleModel, Instrument as InstrumentModel, SyncRun
from apps.market_data.infrastructure.repositories import CandleRepository, InstrumentRepository
from core.utils import to_utc


class Command(BaseCommand):
    help = "Import historical OHLCV data from CSV files into Candle table."

    def add_arguments(self, parser) -> None:
        parser.add_argument(
            "--csv-dir",
            dest="csv_dir",
            required=True,
            help="Directory containing CSV files (one per symbol).",
        )
        parser.add_argument(
            "--symbols",
            dest="symbols",
            default="",
            help="Comma-separated symbols to import (default: all CSV files in directory).",
        )
        parser.add_argument(
            "--timeframe",
            dest="timeframe",
            default="1D",
            help="Candle timeframe (default: 1D).",
        )
        parser.add_argument(
            "--exchange",
            dest="exchange",
            default="NSE",
            help="Exchange code (default: NSE).",
        )
        parser.add_argument(
            "--dry-run",
            dest="dry_run",
            action="store_true",
            help="Parse and validate CSV files without persisting.",
        )
        parser.add_argument(
            "--skip-existing",
            dest="skip_existing",
            action="store_true",
            help="Skip symbols that already have candle data for this timeframe.",
        )

    def handle(self, *args: Any, **options: Any) -> None:
        csv_dir = Path(options["csv_dir"])
        if not csv_dir.exists() or not csv_dir.is_dir():
            raise CommandError(f"CSV directory does not exist: {csv_dir}")

        timeframe = self._parse_timeframe(options["timeframe"])
        exchange = options["exchange"].upper()
        dry_run = options["dry_run"]
        skip_existing = options["skip_existing"]

        # Resolve symbols
        symbols = self._resolve_symbols(csv_dir, options["symbols"])
        if not symbols:
            raise CommandError("No symbols to import. Provide --symbols or ensure CSV files exist.")

        self.stdout.write(
            f"Importing {len(symbols)} symbols from {csv_dir} "
            f"(timeframe={timeframe.value}, exchange={exchange}, dry_run={dry_run})"
        )

        instrument_repo = InstrumentRepository()
        candle_repo = CandleRepository()

        # Ensure instruments exist (create if missing for CSV import)
        instruments = self._ensure_instruments(instrument_repo, symbols, exchange)

        total_rows = 0
        results = []

        for tradingsymbol, instrument_token in instruments:
            csv_path = csv_dir / f"{tradingsymbol}.csv"
            if not csv_path.exists():
                self.stderr.write(self.style.WARNING(f"  [{tradingsymbol}] CSV not found: {csv_path}"))
                continue

            # Check if candles already exist
            if skip_existing:
                existing = CandleModel.objects.filter(
                    instrument_id=instrument_token,
                    timeframe=timeframe.value,
                ).exists()
                if existing:
                    self.stdout.write(f"  [{tradingsymbol}] Skipping (already has data)")
                    continue

            # Create SyncRun record
            sync_run = SyncRun.objects.create(
                source=SyncRun.Source.CSV,
                symbol=tradingsymbol,
                timeframe=timeframe.value,
                range_start=datetime.min.replace(tzinfo=timezone.utc),
                range_end=datetime.max.replace(tzinfo=timezone.utc),
                status=SyncRun.Status.RUNNING,
            )

            try:
                rows_written = self._import_csv(
                    csv_path,
                    instrument_token,
                    timeframe,
                    candle_repo,
                    dry_run,
                )
                total_rows += rows_written

                sync_run.rows_written = rows_written
                sync_run.status = SyncRun.Status.COMPLETED
                sync_run.finished_at = dj_timezone.now()
                sync_run.save()

                self.stdout.write(
                    self.style.SUCCESS(f"  [{tradingsymbol}] OK, {rows_written} candles")
                )
                results.append((tradingsymbol, rows_written, None))

            except Exception as exc:  # noqa: BLE001
                sync_run.status = SyncRun.Status.FAILED
                sync_run.error_message = str(exc)
                sync_run.finished_at = dj_timezone.now()
                sync_run.save()

                self.stderr.write(self.style.ERROR(f"  [{tradingsymbol}] FAILED: {exc}"))
                results.append((tradingsymbol, 0, str(exc)))

        # Summary
        self.stdout.write("---")
        success_count = sum(1 for _, _, err in results if err is None)
        fail_count = len(results) - success_count
        self.stdout.write(
            self.style.SUCCESS(
                f"done: symbols={len(results)} success={success_count} failed={fail_count} "
                f"total_candles={total_rows}"
            )
        )

        if fail_count > 0:
            for symbol, _, err in results:
                if err:
                    self.stderr.write(f"  {symbol}: {err}")
            sys.exit(1)

    def _parse_timeframe(self, raw: str) -> Timeframe:
        try:
            return Timeframe.from_string(raw)
        except ValueError as exc:
            raise CommandError(str(exc))

    def _resolve_symbols(self, csv_dir: Path, symbols_raw: str) -> list[str]:
        """Resolve list of symbols to import."""
        if symbols_raw:
            return [s.strip().upper() for s in symbols_raw.split(",") if s.strip()]

        # Auto-discover from CSV files
        symbols = []
        for csv_file in csv_dir.glob("*.csv"):
            if csv_file.name.startswith("_"):  # Skip quality report etc.
                continue
            symbol = csv_file.stem.upper()
            symbols.append(symbol)
        return sorted(symbols)

    def _ensure_instruments(
        self,
        instrument_repo: InstrumentRepository,
        symbols: list[str],
        exchange: str,
    ) -> list[tuple[str, int]]:
        """Ensure instruments exist in the database, create if missing."""
        instruments = []

        for symbol in symbols:
            sym_obj = Symbol(exchange=exchange, tradingsymbol=symbol)
            existing = instrument_repo.find_by_symbol(sym_obj)

            if existing:
                instruments.append((symbol, existing.instrument_token))
            else:
                # Create a placeholder instrument with a synthetic token
                # In production, this should be reconciled with the broker's instrument master
                import hashlib
                synthetic_token = int(hashlib.md5(f"{exchange}:{symbol}".encode()).hexdigest()[:15], 16)

                # Check if token already exists
                while instrument_repo.find_by_token(synthetic_token):
                    synthetic_token += 1

                instrument = instrument_repo.save(
                    type("Instrument", (), {
                        "instrument_token": synthetic_token,
                        "exchange": exchange,
                        "tradingsymbol": symbol,
                        "name": symbol,
                        "segment": "EQUITY",
                        "lot_size": 1,
                        "tick_size": Decimal("0.05"),
                        "instrument_type": "EQ",
                        "expiry": None,
                        "is_active": True,
                    })()
                )
                instruments.append((symbol, instrument.instrument_token))
                self.stdout.write(f"  [{symbol}] Created instrument with synthetic token {synthetic_token}")

        return instruments

    def _import_csv(
        self,
        csv_path: Path,
        instrument_token: int,
        timeframe: Timeframe,
        candle_repo: CandleRepository,
        dry_run: bool,
    ) -> int:
        """Import a single CSV file."""
        candles = []

        with csv_path.open("r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            required_columns = {"date", "open", "high", "low", "close", "volume", "symbol"}
            if not required_columns.issubset(set(reader.fieldnames or [])):
                raise CommandError(
                    f"CSV {csv_path} missing required columns. "
                    f"Required: {required_columns}, Got: {set(reader.fieldnames or [])}"
                )

            for row in reader:
                try:
                    timestamp = datetime.fromisoformat(row["date"]).replace(tzinfo=timezone.utc)
                    candles.append(
                        type("Candle", (), {
                            "instrument_token": instrument_token,
                            "timeframe": timeframe.value,
                            "timestamp": timestamp,
                            "open": Decimal(row["open"]),
                            "high": Decimal(row["high"]),
                            "low": Decimal(row["low"]),
                            "close": Decimal(row["close"]),
                            "volume": int(row["volume"]),
                        })()
                    )
                except (ValueError, KeyError) as exc:
                    self.stderr.write(
                        self.style.WARNING(f"    Skipping invalid row: {row} ({exc})")
                    )
                    continue

        if not dry_run and candles:
            # Use bulk_upsert for efficiency
            return candle_repo.bulk_upsert(candles)

        return len(candles)