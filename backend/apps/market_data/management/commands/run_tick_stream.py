"""Long-running Kite Ticker (WebSocket) -> candle pipeline process.

LIVE-PAPER-DRESS-REHEARSAL-1. Hard off by default: refuses to start unless

    MARKET_DATA_PROVIDER=zerodha_ticker

is explicitly configured. When enabled, this command assembles the full
live-data bridge and blocks until SIGTERM/SIGINT:

    ZerodhaTickerAdapter (kiteconnect.KiteTicker, threaded)
      -> WebSocketTickManager (session-aware lifecycle, backoff, Redis state)
        -> TickToCandleAggregator (1-min OHLCV buckets from tick extremes)
          -> CandleRepository.upsert
          -> CandleToTechnicalAnalysisBridge.ingest_fresh_candle
            -> TA ingestion -> EventBus -> intelligence -> rule engine
               -> risk -> paper execution   [same seam as REST polling]

Instrument subscription defaults to the configured
``MARKET_DATA_POLL_WATCHLIST`` pairs so streaming covers exactly the symbols
the REST poller would have covered; override with ``--symbols``.

Run it in its own container/process (a dedicated worker), NOT inside a Celery
worker fork — the WebSocket thread must outlive individual task executions::

    docker compose run --rm backend \
        MARKET_DATA_PROVIDER=zerodha_ticker python manage.py run_tick_stream
"""

from __future__ import annotations

from typing import Any

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError


class Command(BaseCommand):
    help = (
        "Stream live ticks via the Kite WebSocket into the standard candle->TA "
        "event pipeline (paper dress rehearsal). Requires "
        "MARKET_DATA_PROVIDER=zerodha_ticker."
    )

    def add_arguments(self, parser) -> None:
        parser.add_argument(
            "--symbols",
            default="",
            help="Comma-separated SYMBOL list to stream; default = MARKET_DATA_POLL_WATCHLIST.",
        )
        parser.add_argument(
            "--exchange",
            default="NSE",
            help="Exchange for symbol resolution (default NSE).",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Resolve instruments, print what would be streamed, exit.",
        )

    # ------------------------------------------------------------------
    def handle(self, *args: Any, **options: Any) -> None:
        provider = str(getattr(settings, "MARKET_DATA_PROVIDER", "mock"))
        if provider != "zerodha_ticker":
            raise CommandError(
                f"run_tick_stream is config-gated: set MARKET_DATA_PROVIDER=zerodha_ticker "
                f"(current: {provider!r}). This is deliberate — the live stream is OFF by default."
            )

        timeframe = str(getattr(settings, "MARKET_DATA_POLL_TIMEFRAME", "1min"))
        bucket_seconds = max(1, int(getattr(settings, "MARKET_DATA_TICK_BUCKET_SECONDS", 60)))

        symbols = self._resolve_symbols(options["symbols"])
        if not symbols:
            raise CommandError(
                "No symbols to stream: pass --symbols or configure MARKET_DATA_POLL_WATCHLIST."
            )

        instruments = self._resolve_instruments(symbols, options["exchange"])
        if not instruments:
            raise CommandError(
                f"No Instrument rows matched {symbols} on {options['exchange']}. "
                "Run sync_instrument_master first."
            )

        self.stdout.write(
            f"Streaming {len(instruments)} instruments on {timeframe} "
            f"({bucket_seconds}s buckets): "
            + ", ".join(f"{sym}=#{tok}" for sym, tok in instruments)
        )
        if options["dry_run"]:
            return

        self._run(instruments, timeframe, bucket_seconds)

    # ------------------------------------------------------------------
    def _resolve_symbols(self, raw: str) -> list[str]:
        if raw.strip():
            return [s.strip().upper() for s in raw.split(",") if s.strip()]
        watchlist = getattr(settings, "MARKET_DATA_POLL_WATCHLIST", []) or []
        return sorted({symbol for _exchange, symbol in watchlist})

    def _resolve_instruments(self, symbols: list[str], exchange: str) -> list[tuple[str, int]]:
        from apps.market_data.infrastructure.models import Instrument

        rows = Instrument.objects.filter(
            exchange=exchange.upper(), tradingsymbol__in=symbols
        ).values_list("tradingsymbol", "instrument_token")
        by_symbol = {sym: int(tok) for sym, tok in rows}
        return [(sym, by_symbol[sym]) for sym in symbols if sym in by_symbol]

    def _run(self, instruments: list[tuple[str, int]], timeframe: str, bucket_seconds: int) -> None:
        # Deferred imports: heavy/optional deps load only when actually running.
        from apps.market_data.application.candle_ta_bridge import get_candle_ta_bridge
        from apps.market_data.application.tick_to_candle_aggregator import (
            TickToCandleAggregator,
        )
        from apps.market_data.infrastructure.providers.zerodha_ticker_adapter import (
            ZerodhaTickerAdapter,
        )
        from apps.market_data.infrastructure.websocket_manager import (
            WebSocketTickManager,
        )

        bridge = get_candle_ta_bridge()

        def on_candle(instrument_token: int, timestamp) -> None:
            # Same seam as the REST polling path — staleness gate, payload
            # build and TA ingestion all happen inside the bridge.
            try:
                bridge.ingest_fresh_candle(
                    instrument_token=instrument_token,
                    timeframe=timeframe,
                    candle_timestamp=timestamp,
                )
            except Exception:  # noqa: BLE001 - one symbol must not kill the stream
                self.stderr.write(f"bridge ingest failed for token {instrument_token}")

        aggregator = TickToCandleAggregator(
            timeframe=timeframe,
            bucket_seconds=bucket_seconds,
            on_candle=on_candle,
        )
        manager = WebSocketTickManager(
            tick_source=ZerodhaTickerAdapter(),
            on_tick=aggregator.handle_quote,
        )
        manager.subscribe([token for _sym, token in instruments])

        WebSocketTickManager.install_signal_handlers(manager)
        manager.start()
        self.stdout.write(self.style.SUCCESS("tick stream started; Ctrl+C to stop"))

        # Block the main thread; the manager owns a daemon worker thread and
        # the KiteTicker runs in its own thread. Signals stop `manager`.
        import time

        try:
            while manager.is_running:
                time.sleep(5)
        except KeyboardInterrupt:
            pass
        finally:
            persisted = aggregator.flush()
            manager.stop()
            self.stdout.write(f"tick stream stopped (flushed {persisted} in-flight buckets)")
