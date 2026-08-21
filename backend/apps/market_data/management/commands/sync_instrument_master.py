"""
Management command: sync_instrument_master

Synchronize the local Instrument table with the broker's instrument master.
Currently supports Zerodha/Kite Connect via the existing Zerodha provider's
fetch_instruments() method.

This command:
1. Fetches the full instrument master from the active provider (Zerodha)
2. Filters for NIFTY 50 equity symbols (NSE:EQ segment)
3. Upserts instruments into the local table
4. Marks instruments not in the master as inactive
5. Creates a SyncRun audit record

Usage::

    python manage.py sync_instrument_master \\
        --symbols RELIANCE,TCS,INFY \\
        --segment EQUITY \\
        --exchange NSE

    python manage.py sync_instrument_master \\
        --all  # sync all instruments from master (may be large)
"""

from __future__ import annotations

import sys
from datetime import datetime, timezone
from typing import Any

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone as dj_timezone

from apps.market_data.application.instrument_sync_service import get_instrument_sync_service
from apps.market_data.infrastructure.models import Instrument as InstrumentModel, SyncRun
from apps.market_data.infrastructure.repositories import InstrumentRepository
from core.market_data.provider_factory import MarketDataProviderFactory


class Command(BaseCommand):
    help = "Sync local Instrument table with broker's instrument master."

    def add_arguments(self, parser) -> None:
        parser.add_argument(
            "--symbols",
            dest="symbols",
            default="",
            help="Comma-separated symbols to sync (default: all NSE equity instruments).",
        )
        parser.add_argument(
            "--segment",
            dest="segment",
            default="EQUITY",
            help="Market segment to filter (default: EQUITY).",
        )
        parser.add_argument(
            "--exchange",
            dest="exchange",
            default="NSE",
            help="Exchange code (default: NSE).",
        )
        parser.add_argument(
            "--all",
            dest="sync_all",
            action="store_true",
            help="Sync all instruments from master (not just filtered).",
        )
        parser.add_argument(
            "--provider",
            dest="provider",
            default=None,
            help="Market data provider to use (default: settings.MARKET_DATA_PROVIDER).",
        )
        parser.add_argument(
            "--dry-run",
            dest="dry_run",
            action="store_true",
            help="Fetch and report what would be synced without persisting.",
        )

    def handle(self, *args: Any, **options: Any) -> None:
        provider_name = options["provider"]
        if provider_name:
            settings.MARKET_DATA_PROVIDER = provider_name
            MarketDataProviderFactory.reset()

        segment = options["segment"].upper()
        exchange = options["exchange"].upper()
        sync_all = options["sync_all"]
        dry_run = options["dry_run"]
        symbols_filter = options["symbols"]

        self.stdout.write(
            f"Syncing instrument master (provider={settings.MARKET_DATA_PROVIDER}, "
            f"segment={segment}, exchange={exchange}, dry_run={dry_run})"
        )

        # Create SyncRun record
        sync_run = SyncRun.objects.create(
            source=SyncRun.Source.ZERODHA,
            symbol="INSTRUMENT_MASTER",
            timeframe="N/A",
            range_start=datetime.min.replace(tzinfo=timezone.utc),
            range_end=datetime.max.replace(tzinfo=timezone.utc),
            status=SyncRun.Status.RUNNING,
        )

        try:
            if dry_run:
                result = self._dry_run_sync(segment, exchange, symbols_filter, sync_all)
            else:
                result = self._run_sync(segment, exchange, symbols_filter, sync_all)

            sync_run.rows_written = result.get("created", 0) + result.get("updated", 0)
            sync_run.status = SyncRun.Status.COMPLETED
            sync_run.finished_at = dj_timezone.now()
            sync_run.save()

            total = result.get("total", result.get("created", 0) + result.get("updated", 0))
            self.stdout.write(
                self.style.SUCCESS(
                    f"done: created={result['created']} updated={result['updated']} "
                    f"deactivated={result['deactivated']} merged={result.get('merged', 0)} "
                    f"total={total}"
                )
            )

        except Exception as exc:  # noqa: BLE001
            sync_run.status = SyncRun.Status.FAILED
            sync_run.error_message = str(exc)
            sync_run.finished_at = dj_timezone.now()
            sync_run.save()

            self.stderr.write(self.style.ERROR(f"FAILED: {exc}"))
            sys.exit(1)

    def _dry_run_sync(
        self,
        segment: str,
        exchange: str,
        symbols_filter: str,
        sync_all: bool,
    ) -> dict[str, int]:
        """Fetch instrument master and report what would be synced."""
        provider = MarketDataProviderFactory.get_provider()
        if not hasattr(provider, "fetch_instruments"):
            raise CommandError(f"Provider {provider.provider_name} does not support fetch_instruments()")

        self.stdout.write("Fetching instrument master from provider...")
        raw_instruments = provider.fetch_instruments()
        self.stdout.write(f"Fetched {len(raw_instruments)} instruments from master")

        # Filter instruments
        filtered = self._filter_instruments(raw_instruments, segment, exchange, symbols_filter, sync_all)
        self.stdout.write(f"After filtering: {len(filtered)} instruments")

        # Compare with local
        repo = InstrumentRepository()
        local_tokens = set()
        for inst in InstrumentModel.objects.filter(is_active=True).values_list("instrument_token", flat=True):
            local_tokens.add(inst)

        upstream_tokens = {inst["instrument_token"] for inst in filtered}

        to_create = [inst for inst in filtered if inst["instrument_token"] not in local_tokens]
        to_update = [inst for inst in filtered if inst["instrument_token"] in local_tokens]
        to_deactivate = local_tokens - upstream_tokens

        self.stdout.write(f"Would create: {len(to_create)}")
        self.stdout.write(f"Would update: {len(to_update)}")
        self.stdout.write(f"Would deactivate: {len(to_deactivate)}")

        if to_create:
            self.stdout.write("  Sample creates:")
            for inst in to_create[:5]:
                self.stdout.write(f"    {inst['exchange']}:{inst['tradingsymbol']} (token={inst['instrument_token']})")

        return {
            "created": len(to_create),
            "updated": len(to_update),
            "deactivated": len(to_deactivate),
            "total": len(filtered),
        }

    def _run_sync(
        self,
        segment: str,
        exchange: str,
        symbols_filter: str,
        sync_all: bool,
    ) -> dict[str, int]:
        """Run the actual sync using InstrumentSyncService, then filter results."""
        # Use the existing sync service
        service = get_instrument_sync_service()
        result = service.sync()

        # If we have a specific symbol filter, report on those
        if symbols_filter and not sync_all:
            symbols = [s.strip().upper() for s in symbols_filter.split(",") if s.strip()]
            self.stdout.write(f"Filtered for symbols: {symbols}")

            for symbol in symbols:
                inst = InstrumentRepository().find_by_symbol(
                    type("Symbol", (), {"exchange": exchange, "tradingsymbol": symbol})()
                )
                if inst:
                    self.stdout.write(f"  {symbol}: token={inst.instrument_token}")
                else:
                    self.stdout.write(self.style.WARNING(f"  {symbol}: NOT FOUND in master"))

        return result

    def _filter_instruments(
        self,
        raw_instruments: list[dict[str, Any]],
        segment: str,
        exchange: str,
        symbols_filter: str,
        sync_all: bool,
    ) -> list[dict[str, Any]]:
        """Filter instruments by segment, exchange, and optional symbol list."""
        filtered = []

        symbols_set = set()
        if symbols_filter:
            symbols_set = {s.strip().upper() for s in symbols_filter.split(",") if s.strip()}

        for inst in raw_instruments:
            # Filter by exchange
            if inst.get("exchange", "").upper() != exchange:
                continue

            # Filter by segment
            if inst.get("segment", "").upper() != segment:
                continue

            # Filter by instrument type (equity only)
            if inst.get("instrument_type", "").upper() not in ("EQ", "EQUITY"):
                continue

            # Filter by symbol list if provided
            if symbols_set and inst.get("tradingsymbol", "").upper() not in symbols_set:
                continue

            filtered.append(inst)

        return filtered