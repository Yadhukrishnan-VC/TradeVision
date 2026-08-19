"""
Management command: backfill_historical

CLI entrypoint for ``HistoricalSyncService`` — the same backfill the Celery
task path uses, exposed for operational use. Wraps the existing service
without changing its logic; ``--dry-run`` fetches through the active provider
(identical request contract) and reports what would be persisted without
writing anything.

Usage::

    python manage.py backfill_historical \\
        --provider=paper --symbols=RELIANCE,INFY \\
        --timeframe=1min --days=5

    python manage.py backfill_historical \\
        --provider=zerodha --symbols=NSE:RELIANCE \\
        --from=2026-08-01T00:00:00+00:00 --to=2026-08-05T00:00:00+00:00

    python manage.py backfill_historical --tokens=12345,67890 --dry-run

Symbols are resolved to instrument tokens via ``InstrumentRepository``; use
``EXCHANGE:SYMBOL`` or rely on ``MARKET_EXCHANGE`` for the exchange. At least
one of ``--symbols``/``--tokens`` and exactly one of ``--from``/``--days`` is
required. The command exits non-zero if any instrument fails.
"""

from __future__ import annotations

import sys
from datetime import datetime, timedelta, timezone
from typing import Any

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from apps.common.domain.value_objects import Symbol
from apps.market_data.application.historical_sync_service import (
    get_historical_sync_service,
)
from apps.market_data.domain.value_objects import Timeframe
from apps.market_data.infrastructure.repositories import InstrumentRepository
from core.market_data.base_provider import MarketDataRequest
from core.market_data.provider_factory import MarketDataProviderFactory
from core.utils import get_now, to_utc

_KNOWN_PROVIDERS = frozenset({"mock", "paper", "zerodha"})

_HELP_PROVIDER = "Market data provider (mock, paper, zerodha). Default: settings.MARKET_DATA_PROVIDER."
_HELP_SYMBOLS = "Comma-separated symbols, each EXCHANGE:SYMBOL or SYMBOL (default exchange from MARKET_EXCHANGE)."
_HELP_TOKENS = "Comma-separated instrument tokens (alternative to --symbols)."
_HELP_TIMEFRAME = "Candle interval, e.g. 1min, 5min, 1D. Default: 1min."
_HELP_FROM = "Start of range (ISO-8601, UTC). Mutually exclusive with --days."
_HELP_TO = "End of range (ISO-8601, UTC). Default: now."
_HELP_DAYS = "Days of history before --to/now. Mutually exclusive with --from."
_HELP_DRYRUN = "Fetch and report bar counts without persisting anything."


class Command(BaseCommand):
    help = "Backfill historical candles through HistoricalSyncService."

    def add_arguments(self, parser) -> None:
        parser.add_argument(
            "--provider", dest="provider", default=None, help=_HELP_PROVIDER
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

    def handle(self, *args: Any, **options: Any) -> None:
        timeframe = self._parse_timeframe(options["timeframe"])
        start, end = self._parse_range(
            options["from_ts"], options["to_ts"], options["days"]
        )
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
            f"mode={'dry-run' if options['dry_run'] else 'persist'} "
            f"instruments={len(instruments)}"
        )

        failures: list[str] = []
        persisted_total = 0
        bars_total = 0

        for token, label in instruments:
            self.stdout.write(f"  [{label}] fetching ...", ending="\r")
            try:
                if options["dry_run"]:
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
