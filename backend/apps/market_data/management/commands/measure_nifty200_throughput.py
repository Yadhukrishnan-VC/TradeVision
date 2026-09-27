"""Measure NIFTY200 polling throughput through the real cycle path.

Simulates a live trading-day poll: forces a market-hours clock, seeds the
NIFTY200 universe + instruments, runs full rotating-batch cycles through
``poll_watchlist_sync`` (the exact Celery ``poll_market_data_watchlist`` code
path, including per-symbol session-frame backfill gates and the token-bucket
pacing at ``MARKET_DATA_POLL_RATE_LIMIT_PER_SECOND``), and reports:

    * requests per cycle (paced by the token bucket at the Kite cap),
    * effective provider request rate seen by the upstream (req/s),
    * elapsed wall-clock per cycle vs ``CELERY_TASK_TIME_LIMIT`` (60s),
    * cycles needed for a full universe sweep and total elapsed time.

The provider is a fast in-process fake (no network), so the numbers isolate
the rate-limit pacing + ORM overhead of a real sweep without depending on
Zerodha credentials or NSE being open.
"""

from __future__ import annotations

import time as _time
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from zoneinfo import ZoneInfo

from django.conf import settings
from django.core.management.base import BaseCommand
from django.db import transaction

from apps.common.domain.value_objects import Symbol
from apps.market_data.application.universe_service import resolve_universe
from apps.market_data.infrastructure import polling_tasks
from apps.market_data.infrastructure.models import IndexConstituent, Instrument
from apps.market_data.infrastructure.repositories import InstrumentRepository
from core.market_data.base_provider import (
    BaseMarketDataProvider,
    MarketDataRequest,
    MarketDataResponse,
    OHLCVBar,
)

_IST = ZoneInfo("Asia/Kolkata")


class HarnessCalendar:
    def get_session(self, dt: datetime):
        from core.market_calendar import MarketSession

        return MarketSession.MARKET_HOURS


def _bar(ts: datetime, close: str = "100.5") -> OHLCVBar:
    return OHLCVBar(
        timestamp=ts,
        open_price=Decimal("100"),
        high=Decimal("101"),
        low=Decimal("99"),
        close_price=Decimal(close),
        volume=90_000,
    )


class CountingProvider(BaseMarketDataProvider):
    """Tiny deterministic provider that counts ``fetch`` calls."""

    provider_name = "counting"

    def __init__(self) -> None:
        self.fetches = 0

    def fetch(self, request: MarketDataRequest) -> MarketDataResponse:
        self.fetches += 1
        interval = request.interval
        start = request.from_timestamp or (datetime.now(timezone.utc) - timedelta(days=30))
        if interval == "1D":
            bars = [_bar(start + timedelta(days=day), close="103") for day in range(30)]
        elif interval == "15min":
            bars = [_bar(start + timedelta(days=day), close="100.5") for day in range(16)]
        else:
            bars = [
                _bar(datetime.now(timezone.utc) - timedelta(seconds=240)),
                _bar(datetime.now(timezone.utc) - timedelta(seconds=60), close="102"),
            ]
        return MarketDataResponse(
            request_id=request.request_id,
            symbol=request.symbol,
            interval=interval,
            bars=tuple(bars),
            provider=self.provider_name,
            fetched_at=datetime.now(timezone.utc),
        )

    def validate_connection(self) -> bool:
        return True

    def health_check(self):
        return {"status": "healthy", "provider": self.provider_name, "latency_ms": 0.1}

    def close(self) -> None:
        pass


class Command(BaseCommand):
    help = "Measure NIFTY200 universe polling throughput (paced, market-hours clock)."

    def add_arguments(self, parser) -> None:
        parser.add_argument(
            "--cycles",
            type=int,
            default=0,
            help="Number of poll cycles to run (0 = full universe sweep + 1 cycle).",
        )
        parser.add_argument(
            "--batch-size",
            type=int,
            default=None,
            help="Override MARKET_DATA_POLL_BATCH_SIZE.",
        )
        parser.add_argument(
            "--rate",
            type=float,
            default=None,
            help="Override MARKET_DATA_POLL_RATE_LIMIT_PER_SECOND.",
        )

    @transaction.atomic
    def _seed(self) -> int:
        """Seed one Instrument for every active constituent; idempotent."""
        rows = (
            IndexConstituent.objects.filter(is_active=True)
            .order_by("sort_order", "tradingsymbol")
            .values_list("exchange", "tradingsymbol")
        )
        existing = set(
            Instrument.objects.filter(exchange="NSE").values_list(
                "tradingsymbol", flat=True
            )
        )
        created = 0
        for idx, (exchange, symbol) in enumerate(rows, start=1):
            if symbol in existing:
                continue
            Instrument.objects.create(
                instrument_token=1_000_000_000 + idx,
                exchange=exchange,
                tradingsymbol=symbol,
                name=symbol,
                segment="EQUITY",
                lot_size=1,
                tick_size=Decimal("0.05"),
                instrument_type="EQUITY",
                is_active=True,
            )
            created += 1
        return created

    def handle(self, *args, **options) -> None:
        from unittest.mock import patch

        from core.redis_client import get_redis_client

        if options["batch_size"]:
            settings.MARKET_DATA_POLL_BATCH_SIZE = options["batch_size"]
        if options["rate"]:
            settings.MARKET_DATA_POLL_RATE_LIMIT_PER_SECOND = options["rate"]

        batch_size = int(settings.MARKET_DATA_POLL_BATCH_SIZE or 0)
        rate_per_sec = float(settings.MARKET_DATA_POLL_RATE_LIMIT_PER_SECOND or 0)

        universe = resolve_universe()
        if not universe:
            self.stderr.write("No universe resolved; sync constituents first.")
            return

        created = self._seed()
        self.stdout.write(
            f"universe={len(universe)} instruments_seeded={created} "
            f"batch_size={batch_size} rate={rate_per_sec}"
        )

        provider = CountingProvider()
        redis_client = get_redis_client()
        redis_client.delete("tradevision:market_data:poll_universe:cursor")
        polling_tasks._poll_rate_limiter = None

        now_ist = datetime(2026, 9, 24, 9, 30, tzinfo=_IST)  # Thursday, market-open
        patches = [
            patch(
                "apps.market_data.infrastructure.polling_tasks.get_now",
                lambda: now_ist,
            ),
            patch(
                "apps.market_data.infrastructure.polling_tasks.get_ist_now",
                lambda: now_ist,
            ),
            patch(
                "apps.market_data.infrastructure.polling_tasks.get_market_calendar",
                lambda: HarnessCalendar(),
            ),
            patch(
                "apps.market_data.application.historical_sync_service.MarketDataProviderFactory._instance",
                provider,
            ),
            patch(
                "apps.market_data.application.candle_ta_bridge.get_now",
                lambda: now_ist,
            ),
        ]
        for p in patches:
            p.start()

        try:
            instrument_repo = InstrumentRepository()

            def _symbols_ok(batch) -> str:
                missing = [
                    sym
                    for (_ex, sym) in batch
                    if instrument_repo.find_by_symbol(
                        Symbol(exchange=_ex, tradingsymbol=sym)
                    )
                    is None
                ]
                return "" if not missing else f" MISSING_INSTRUMENTS={missing[:5]}"

            cycles = options["cycles"] or 0
            covered: set[str] = set()
            total_cycles = 0
            total_elapsed = 0.0
            cycle_rows: list[tuple[int, int, int, float, int]] = []
            saw_full = False
            while True:
                batch = polling_tasks._resolve_poll_batch()
                if not batch:
                    break
                start = _time.monotonic()
                published = polling_tasks.poll_watchlist_sync(batch)
                elapsed = _time.monotonic() - start
                total_cycles += 1
                total_elapsed += elapsed
                covered.update(s for (_ex, s) in batch)
                cycle_rows.append(
                    (total_cycles, len(batch), published, elapsed, provider.fetches)
                )
                self.stdout.write(
                    f"cycle={total_cycles} batch={len(batch)} published={published} "
                    f"elapsed={elapsed:.1f}s fetches={provider.fetches} "
                    f"covered={len(covered)}/{len(universe)} {_symbols_ok(batch)}"
                )
                if len(covered) >= len(universe):
                    if saw_full and not cycles:
                        break
                    saw_full = True
                if cycles and total_cycles >= cycles:
                    break

            self.stdout.write("=" * 72)
            self.stdout.write("THROUGHPUT MEASUREMENT (NIFTY200 polling, paced)")
            self.stdout.write(
                f"universe={len(universe)} batch_size={batch_size} "
                f"rate_limit={rate_per_sec}/s"
            )
            self.stdout.write(f"cycles={total_cycles} covered={len(covered)}")
            if cycle_rows:
                last = cycle_rows[-1]
                fetches = last[4]
                eff_rate = fetches / total_elapsed if total_elapsed else 0
                self.stdout.write(
                    f"total_elapsed={total_elapsed:.1f}s total_provider_fetches={fetches} "
                    f"effective_provider_rate={eff_rate:.2f} req/s "
                    f"(limit {rate_per_sec}/s)"
                )
                self.stdout.write(
                    f"max_cycle_elapsed={max(r[3] for r in cycle_rows):.1f}s "
                    f"(CELERY_TASK_TIME_LIMIT=60s)"
                )
                if rate_per_sec and eff_rate > rate_per_sec * 1.02:
                    self.stdout.write(
                        self.style.WARNING(
                            f"WARNING: effective rate {eff_rate:.2f} exceeds cap "
                            f"{rate_per_sec}/s — pacing not holding."
                        )
                    )
                else:
                    self.stdout.write(
                        self.style.SUCCESS(
                            f"pacing-holds: effective rate {eff_rate:.2f} req/s <= "
                            f"cap {rate_per_sec}/s"
                        )
                    )
        finally:
            for p in patches:
                p.stop()
            redis_client.delete("tradevision:market_data:poll_universe:cursor")