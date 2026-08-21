"""Management command: backfill_ta

Rebuild ``TASnapshot`` history from already-persisted ``Candle`` rows using the
*unchanged* ``CandleToTechnicalAnalysisBridge.backfill_ta_from_candles`` seam
(same payload builder, same indicator computation, same ingestion service).

The bridge is idempotent per candle, but the current DB may already contain
duplicate/indicator-less rows (from the backtest runner re-ingesting raw
payloads before indicator keys existed). ``--clean`` removes every existing
``TASnapshot`` row for the target symbols + timeframe first so the rebuilt
history is exactly one snapshot per candle with full indicator keys.

Usage::

    python manage.py backfill_ta --timeframe 1D [--clean] [--dry-run]
    python manage.py backfill_ta --symbols RELIANCE,TCS --clean
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Any

from django.core.management.base import BaseCommand

from apps.market_data.application.candle_ta_bridge import CandleToTechnicalAnalysisBridge
from apps.market_data.infrastructure.models import Candle as CandleModel
from apps.market_data.infrastructure.models import Instrument as InstrumentModel
from apps.technical_analysis.infrastructure.models import TASnapshot as TASnapshotModel


class Command(BaseCommand):
    help = "Rebuild TASnapshot history from persisted Candle rows."

    def add_arguments(self, parser) -> None:
        parser.add_argument(
            "--symbols",
            dest="symbols",
            default="",
            help="Comma-separated symbols to backfill (default: all instruments with candles).",
        )
        parser.add_argument(
            "--timeframe",
            dest="timeframe",
            default="1D",
            help="Candle timeframe to backfill (default: 1D).",
        )
        parser.add_argument(
            "--clean",
            action="store_true",
            dest="clean",
            help="Delete existing TASnapshot rows for target symbols before backfilling.",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            dest="dry_run",
            help="Report what would be cleaned/backfilled without changing anything.",
        )

    def handle(self, *args: Any, **options: Any) -> None:
        timeframe = options["timeframe"]
        clean = options["clean"]
        dry_run = options["dry_run"]

        symbols = self._resolve_symbols(options["symbols"], timeframe)
        if not symbols:
            self.stdout.write(self.style.WARNING("No instruments with candles found."))
            return

        bridge = CandleToTechnicalAnalysisBridge()
        total_created = 0
        total_removed = 0

        for symbol in symbols:
            instrument = self._find_instrument(symbol)
            if instrument is None:
                self.stderr.write(self.style.ERROR(f"{symbol}: no instrument row, skipping."))
                continue

            candles = CandleModel.objects.filter(
                instrument=instrument, timeframe=timeframe
            ).order_by("timestamp")
            if not candles.exists():
                self.stdout.write(self.style.WARNING(f"{symbol}: no candles, skipping."))
                continue

            first_ts = candles.first().timestamp
            last_ts = candles.last().timestamp

            if clean and not dry_run:
                removed = TASnapshotModel.objects.filter(
                    symbol=symbol.upper(), timeframe=timeframe
                ).delete()[0]
                total_removed += removed
                self.stdout.write(
                    self.style.WARNING(f"{symbol}: removed {removed} existing snapshots.")
                )
            elif clean and dry_run:
                existing = TASnapshotModel.objects.filter(
                    symbol=symbol.upper(), timeframe=timeframe
                ).count()
                total_removed += existing
                self.stdout.write(
                    self.style.WARNING(
                        f"{symbol}: (dry-run) would remove {existing} existing snapshots."
                    )
                )

            if dry_run:
                pending = candles.count()
                total_created += pending
                self.stdout.write(
                    f"{symbol}: (dry-run) would backfill {pending} candles "
                    f"({first_ts.date()}..{last_ts.date()})."
                )
                continue

            created = bridge.backfill_ta_from_candles(
                instrument.instrument_token, timeframe, first_ts, last_ts
            )
            total_created += created
            self.stdout.write(
                self.style.SUCCESS(
                    f"{symbol}: backfilled {created} candles "
                    f"({first_ts.date()}..{last_ts.date()})."
                )
            )

        self.stdout.write(
            self.style.SUCCESS(
                f"Done. removed={total_removed} created={total_created} symbols={len(symbols)}"
            )
        )

    def _resolve_symbols(self, symbols_raw: str, timeframe: str) -> list[str]:
        if symbols_raw:
            return [s.strip().upper() for s in symbols_raw.split(",") if s.strip()]
        qs = (
            CandleModel.objects.filter(timeframe=timeframe)
            .values_list("instrument__tradingsymbol", flat=True)
            .distinct()
        )
        return sorted(list(qs))

    @staticmethod
    def _find_instrument(symbol: str) -> Any | None:
        try:
            return InstrumentModel.objects.get(
                exchange="NSE", tradingsymbol=symbol.upper()
            )
        except InstrumentModel.DoesNotExist:
            return None