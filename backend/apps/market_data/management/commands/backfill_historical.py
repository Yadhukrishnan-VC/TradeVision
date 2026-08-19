"""
Management command: backfill_historical

CLI entrypoint for ``HistoricalSyncService`` — the same backfill the Celery
task path uses, exposed for operational use. Wraps the existing service
without changing its logic; ``--dry-run`` fetches through the active provider
(identical request contract) and reports what would be persisted without
writing anything.

Now supports multiple data sources via ``--source``:
- ``zerodha``: Fetch via Zerodha Kite Connect (requires instrument sync)
- ``csv``: Import from CSV files (uses import_historical_csv logic)
- ``provider``: Use the active market data provider (legacy behavior)

Usage::

    python manage.py backfill_historical \\
        --source=zerodha --symbols=RELIANCE,INFY \\
        --timeframe=1min --days=5

    python manage.py backfill_historical \\
        --source=csv --csv-dir /app/data/nifty50_daily \\
        --symbols=RELIANCE,TCS --timeframe=1D

    python manage.py backfill_historical \\
        --provider=paper --symbols=RELIANCE,INFY \\
        --timeframe=1min --days=5  # legacy provider-based usage

Symbols are resolved to instrument tokens via ``InstrumentRepository``; use
``EXCHANGE:SYMBOL`` or rely on ``MARKET_EXCHANGE`` for the exchange. At least
one of ``--symbols``/``--tokens`` and exactly one of ``--from``/``--days`` is
required. The command exits non-zero if any instrument fails.
"""

from __future__ import annotations

import csv
import sys
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path
from typing import Any

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone as dj_timezone

from apps.common.domain.value_objects import Symbol
from apps.market_data.application.historical_sync_service import (
    get_historical_sync_service,
)
from apps.market_data.domain.value_objects import Timeframe
from apps.market_data.infrastructure.models import Candle as CandleModel, SyncRun
from apps.market_data.infrastructure.repositories import CandleRepository, InstrumentRepository
from core.market_data.base_provider import MarketDataRequest
from core.market_data.provider_factory import MarketDataProviderFactory
from core.utils import get_now, to_utc

_KNOWN_PROVIDERS = frozenset({"mock", "paper", "zerodha"})
_KNOWN_SOURCES = frozenset({"zerodha", "csv", "provider"})

_HELP_SOURCE = "Data source: zerodha (Kite Connect), csv (CSV import), provider (active provider). Default: provider."
_HELP_PROVIDER = "Market data provider (mock, paper, zerodha). Used when --source=provider. Default: settings.MARKET_DATA_PROVIDER."
_HELP_SYMBOLS = "Comma-separated symbols, each EXCHANGE:SYMBOL or SYMBOL (default exchange from MARKET_EXCHANGE)."
_HELP_TOKENS = "Comma-separated instrument tokens (alternative to --symbols)."
_HELP_TIMEFRAME = "Candle interval, e.g. 1min, 5min, 1D. Default: 1min."
_HELP_FROM = "Start of range (ISO-8601, UTC). Mutually exclusive with --days."
_HELP_TO = "End of range (ISO-8601, UTC). Default: now."
_HELP_DAYS = "Days of history before --to/now. Mutually exclusive with --from."
_HELP_DRYRUN = "Fetch and report bar counts without persisting anything."
_HELP_CSV_DIR = "Directory containing CSV files (required when --source=csv)."
_HELP_EXCHANGE = "Exchange code for CSV import (default: NSE)."


class Command(BaseCommand):
    help = "Backfill historical candles from various sources (zerodha, csv, provider)."

    def add_arguments(self, parser) -> None:
        parser.add_argument(
            "--source",
            dest="source",
            default="provider",
            help=_HELP_SOURCE,
        )
        parser.add_argument(
            "--provider",
            dest="provider",
            default=None,
            help=_HELP_PROVIDER,
        )
        parser.add_argument("--symbols", dest="symbols", default="", help=_HELP_SYMBOLS)
        parser.add_argument("--tokens", dest="tokens", default="", help=_HELP_TOKENS)
        parser.add_argument(
            "--timeframe", dest="timeframe", default="1min", help=_HELP_TIMEFRAME
        )
        parser.add_argument("--from", dest="from_ts", default=None, help=_HELP_FROM)
        parser.add_argument("--to", dest="to_ts", default=None, help=_HELP_TO)
        parser.add_argument(
            "--days", dest="days", type=int, default=None, help=_HELP_DAYS
        )
        parser.add_argument(
            "--dry-run", dest="dry_run", action="store_true", help=_HELP_DRYRUN
        )
        parser.add_argument(
            "--csv-dir",
            dest="csv_dir",
            default=None,
            help=_HELP_CSV_DIR,
        )
        parser.add_argument(
            "--exchange",
            dest="exchange",
            default="NSE",
            help=_HELP_EXCHANGE,
        )

    def handle(self, *args: Any, **options: Any) -> None:
        source = options["source"].lower()
        if source not in _KNOWN_SOURCES:
            raise CommandError(
                f"Unknown source {source!r}. Supported: {sorted(_KNOWN_SOURCES)}."
            )

        timeframe = self._parse_timeframe(options["timeframe"])
        start, end = self._parse_range(
            options["from_ts"], options["to_ts"], options["days"]
        )
        dry_run = options["dry_run"]

        if source == "csv":
            self._handle_csv_source(options, timeframe, start, end, dry_run)
        elif source == "zerodha":
            self._handle_zerodha_source(options, timeframe, start, end, dry_run)
        else:  # provider
            self._handle_provider_source(options, timeframe, start, end, dry_run)

    # ------------------------------------------------------------------
    # Source-specific handlers
    # ------------------------------------------------------------------
    def _handle_csv_source(
        self,
        options: dict[str, Any],
        timeframe: Timeframe,
        start: datetime,
        end: datetime,
        dry_run: bool,
    ) -> None:
        """Import from CSV files."""
        csv_dir = Path(options["csv_dir"] or "")
        if not csv_dir.exists() or not csv_dir.is_dir():
            raise CommandError(f"CSV directory does not exist: {csv_dir}. Use --csv-dir.")

        exchange = options["exchange"].upper()
        symbols = self._resolve_symbols(options["symbols"], options["tokens"])

        if not symbols:
            raise CommandError(
                "No symbols to import. Provide --symbols or ensure CSV files exist in --csv-dir."
            )

        self.stdout.write(
            f"source=csv csv_dir={csv_dir} timeframe={timeframe.value} "
            f"range={start.isoformat()} -> {end.isoformat()} "
            f"mode={'dry-run' if dry_run else 'persist'} symbols={len(symbols)}"
        )

        instrument_repo = InstrumentRepository()
        candle_repo = CandleRepository()

        # Ensure instruments exist
        instruments = self._ensure_instruments(instrument_repo, symbols, exchange)

        total_rows = 0
        results = []

        for tradingsymbol, instrument_token in instruments:
            csv_path = csv_dir / f"{tradingsymbol}.csv"
            if not csv_path.exists():
                self.stderr.write(self.style.WARNING(f"  [{tradingsymbol}] CSV not found: {csv_path}"))
                continue

            # Create SyncRun record
            sync_run = SyncRun.objects.create(
                source=SyncRun.Source.CSV,
                symbol=tradingsymbol,
                timeframe=timeframe.value,
                range_start=start,
                range_end=end,
                status=SyncRun.Status.RUNNING,
            )

            try:
                rows_written = self._import_csv(
                    csv_path,
                    instrument_token,
                    timeframe,
                    candle_repo,
                    dry_run,
                    start,
                    end,
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

        self._print_summary(results, total_rows)

    def _handle_zerodha_source(
        self,
        options: dict[str, Any],
        timeframe: Timeframe,
        start: datetime,
        end: datetime,
        dry_run: bool,
    ) -> None:
        """Fetch from Zerodha Kite Connect."""
        # Force provider to zerodha
        settings.MARKET_DATA_PROVIDER = "zerodha"
        MarketDataProviderFactory.reset()

        provider = "zerodha"
        instruments = self._resolve_instruments(options["symbols"], options["tokens"])

        if not instruments:
            raise CommandError(
                "No instruments resolved. Provide --symbols or --tokens with "
                "instrument rows present in the database. Run instrument sync first."
            )

        self.stdout.write(
            f"provider={provider} timeframe={timeframe.value} "
            f"range={start.isoformat()} -> {end.isoformat()} "
            f"mode={'dry-run' if dry_run else 'persist'} instruments={len(instruments)}"
        )

        failures: list[str] = []
        persisted_total = 0
        bars_total = 0

        for token, label in instruments:
            self.stdout.write(f"  [{label}] fetching ...", ending="\r")
            try:
                if dry_run:
                    bars = self._dry_run(provider, label, timeframe, start, end)
                    bars_total += bars
                    self.stdout.write(
                        self.style.SUCCESS(
                            f"  [{label}] OK dry-run, {bars} bars would be persisted"
                        )
                    )
                else:
                    # Create SyncRun for zerodha
                    sync_run = SyncRun.objects.create(
                        source=SyncRun.Source.ZERODHA,
                        symbol=label.split(":", 1)[1],
                        timeframe=timeframe.value,
                        range_start=start,
                        range_end=end,
                        status=SyncRun.Status.RUNNING,
                    )

                    count = get_historical_sync_service().backfill(
                        instrument_token=token,
                        timeframe=timeframe,
                        from_timestamp=start,
                        to_timestamp=end,
                    )
                    persisted_total += count

                    sync_run.rows_written = count
                    sync_run.status = SyncRun.Status.COMPLETED
                    sync_run.finished_at = dj_timezone.now()
                    sync_run.save()

                    self.stdout.write(
                        self.style.SUCCESS(f"  [{label}] OK, {count} candles persisted")
                    )
            except Exception as exc:  # noqa: BLE001 — per-instrument isolation contract
                failures.append(f"{label}: {exc}")
                self.stderr.write(self.style.ERROR(f"  [{label}] FAILED: {exc}"))

        self.stdout.write("---")
        self.stdout.write(
            self.style.SUCCESS(
                f"done: instruments={len(instruments)} failures={len(failures)} "
                f"candles_persisted={persisted_total} bars_dry_run={bars_total}"
            )
        )
        if failures:
            for failure in failures:
                self.stderr.write(self.style.ERROR(f"  failed: {failure}"))
            sys.exit(1)

    def _handle_provider_source(
        self,
        options: dict[str, Any],
        timeframe: Timeframe,
        start: datetime,
        end: datetime,
        dry_run: bool,
    ) -> None:
        """Use the active market data provider (legacy behavior)."""
        provider = self._resolve_provider(options["provider"])
        instruments = self._resolve_instruments(options["symbols"], options["tokens"])

        if not instruments:
            raise CommandError(
                "No instruments resolved. Provide --symbols or --tokens with "
                "instrument rows present in the database."
            )

        self.stdout.write(
            f"provider={provider} timeframe={timeframe.value} "
            f"range={start.isoformat()} -> {end.isoformat()} "
            f"mode={'dry-run' if dry_run else 'persist'} instruments={len(instruments)}"
        )

        failures: list[str] = []
        persisted_total = 0
        bars_total = 0

        for token, label in instruments:
            self.stdout.write(f"  [{label}] fetching ...", ending="\r")
            try:
                if dry_run:
                    bars = self._dry_run(provider, label, timeframe, start, end)
                    bars_total += bars
                    self.stdout.write(
                        self.style.SUCCESS(
                            f"  [{label}] OK dry-run, {bars} bars would be persisted"
                        )
                    )
                else:
                    count = get_historical_sync_service().backfill(
                        instrument_token=token,
                        timeframe=timeframe,
                        from_timestamp=start,
                        to_timestamp=end,
                    )
                    persisted_total += count
                    self.stdout.write(
                        self.style.SUCCESS(f"  [{label}] OK, {count} candles persisted")
                    )
            except Exception as exc:  # noqa: BLE001 — per-instrument isolation contract
                failures.append(f"{label}: {exc}")
                self.stderr.write(self.style.ERROR(f"  [{label}] FAILED: {exc}"))

        self.stdout.write("---")
        self.stdout.write(
            self.style.SUCCESS(
                f"done: instruments={len(instruments)} failures={len(failures)} "
                f"candles_persisted={persisted_total} bars_dry_run={bars_total}"
            )
        )
        if failures:
            for failure in failures:
                self.stderr.write(self.style.ERROR(f"  failed: {failure}"))
            sys.exit(1)

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------
    def _parse_timeframe(self, raw: str) -> Timeframe:
        try:
            return Timeframe.from_string(raw)
        except ValueError as exc:
            raise CommandError(str(exc))

    def _parse_range(
        self,
        from_ts: str | None,
        to_ts: str | None,
        days: int | None,
    ) -> tuple[datetime, datetime]:
        if bool(from_ts) == bool(days):
            raise CommandError("Provide exactly one of --from or --days.")
        end = self._parse_datetime(to_ts) if to_ts else get_now()
        if days:
            start = end - timedelta(days=days)
        else:
            start = self._parse_datetime(from_ts)
        if start >= end:
            raise CommandError(f"--from ({start}) must be before --to ({end}).")
        return to_utc(start), to_utc(end)

    @staticmethod
    def _parse_datetime(raw: str) -> datetime:
        try:
            dt = datetime.fromisoformat(raw)
        except ValueError as exc:
            raise CommandError(f"Invalid ISO-8601 datetime {raw!r}: {exc}")
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt

    def _resolve_provider(self, provider: str | None) -> str:
        if provider is None:
            provider = getattr(settings, "MARKET_DATA_PROVIDER", "mock")
        provider = provider.lower()
        if provider not in _KNOWN_PROVIDERS:
            raise CommandError(
                f"Unknown provider {provider!r}. Supported: {sorted(_KNOWN_PROVIDERS)}."
            )
        configured = getattr(settings, "MARKET_DATA_PROVIDER", "mock").lower()
        if provider != configured:
            settings.MARKET_DATA_PROVIDER = provider
            MarketDataProviderFactory.reset()
        return provider

    def _resolve_symbols(self, symbols_raw: str, tokens_raw: str) -> list[str]:
        """Resolve list of symbols from --symbols or auto-discover from CSV dir."""
        if symbols_raw:
            return [s.strip().upper() for s in symbols_raw.split(",") if s.strip()]
        return []  # Auto-discovery not implemented for backfill_historical; use --symbols

    def _resolve_instruments(
        self, symbols_raw: str, tokens_raw: str
    ) -> list[tuple[int, str]]:
        if not symbols_raw and not tokens_raw:
            raise CommandError("Provide at least one of --symbols or --tokens.")

        repo = InstrumentRepository()
        default_exchange = getattr(settings, "MARKET_EXCHANGE", "NSE")
        instruments: list[tuple[int, str]] = []

        for symbol_spec in [s.strip() for s in symbols_raw.split(",") if s.strip()]:
            exchange = default_exchange
            tradingsymbol = symbol_spec
            if ":" in symbol_spec:
                exchange, tradingsymbol = symbol_spec.split(":", 1)
                exchange = exchange.strip().upper()
            tradingsymbol = tradingsymbol.strip().upper()
            instrument = repo.find_by_symbol(
                Symbol(exchange=exchange, tradingsymbol=tradingsymbol)
            )
            if instrument is None:
                self.stderr.write(
                    self.style.WARNING(
                        f"  [{exchange}:{tradingsymbol}] not found, skipping"
                    )
                )
                continue
            instruments.append(
                (instrument.instrument_token, f"{exchange}:{tradingsymbol}")
            )

        for token_raw in [t.strip() for t in tokens_raw.split(",") if t.strip()]:
            try:
                token = int(token_raw)
            except ValueError:
                raise CommandError(f"Invalid instrument token {token_raw!r}.")
            instrument = repo.find_by_token(token)
            if instrument is None:
                self.stderr.write(
                    self.style.WARNING(f"  [token {token}] not found, skipping")
                )
                continue
            instruments.append(
                (token, f"{instrument.exchange}:{instrument.tradingsymbol}")
            )

        return instruments

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
                import hashlib
                synthetic_token = int(hashlib.md5(f"{exchange}:{symbol}".encode()).hexdigest()[:15], 16)

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
        range_start: datetime,
        range_end: datetime,
    ) -> int:
        """Import a single CSV file, filtering by date range."""
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
                    # Filter by date range
                    if timestamp < range_start or timestamp > range_end:
                        continue
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
            return candle_repo.bulk_upsert(candles)

        return len(candles)

    def _dry_run(
        self,
        provider: str,
        label: str,
        timeframe: Timeframe,
        start: datetime,
        end: datetime,
    ) -> int:
        tradingsymbol = label.split(":", 1)[1]
        provider_instance = MarketDataProviderFactory.get_provider()
        request = MarketDataRequest(
            symbol=tradingsymbol,
            interval=timeframe.value,
            from_timestamp=to_utc(start),
            to_timestamp=to_utc(end),
        )
        response = provider_instance.fetch(request)
        return len(response.bars)

    def _print_summary(self, results: list[tuple[str, int, str | None]], total_rows: int) -> None:
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