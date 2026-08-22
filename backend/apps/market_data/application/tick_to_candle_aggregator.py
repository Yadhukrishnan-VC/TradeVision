"""In-memory tick -> 1-minute OHLCV candle aggregation (LIVE-PAPER-DRESS-REHEARSAL-1).

Sits between ``ZerodhaTickerAdapter``'s ``Quote`` stream and the exact seam
the REST-polling path uses:

    finalized bucket
      -> ``CandleRepository.upsert``
      -> ``CandleToTechnicalAnalysisBridge.ingest_fresh_candle``
        -> TechnicalAnalysisIngestionService -> EventBus -> intelligence -> ...

so every downstream consumer (TA snapshots, intelligence packets, rule
engine, paper execution, drift monitor) sees ticks and REST polls through
one identical pipeline. Config-gated off by default — see the
``run_tick_stream`` management command.

Kite's ``volume_traded`` is a cumulative session counter, so bucket volume
is computed as the non-negative delta of that counter within the bucket.
"""

from __future__ import annotations

import logging
import threading
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class _Bucket:
    started_at: datetime
    open_: Decimal | None = None
    high: Decimal | None = None
    low: Decimal | None = None
    close: Decimal | None = None
    volume: int = 0

    def add(self, price: Decimal, volume_delta: int) -> None:
        if self.open_ is None:
            self.open_ = price
        self.high = price if self.high is None else max(self.high, price)
        self.low = price if self.low is None else min(self.low, price)
        self.close = price
        self.volume += volume_delta


@dataclass
class _TokenState:
    """Per-token aggregation state: open bucket + cumulative-volume tracker.

    ``last_cum_volume`` intentionally outlives individual buckets — Kite's
    counter is cumulative across the session, and the delta spanning a bucket
    rollover belongs to the *new* bucket.
    """

    bucket: _Bucket | None = None
    last_cum_volume: int | None = None


class TickToCandleAggregator:
    """Accumulates ``Quote`` ticks into fixed-width OHLCV candles.

    Args:
        timeframe:       Timeframe label persisted with the candle (must be a
                         valid ``MARKET_DATA_POLL_TIMEFRAME``; default ``1min``).
        bucket_seconds:  Width of one aggregation bucket in seconds.
        on_candle:       Optional callback invoked as
                         ``(instrument_token, timestamp, o, h, l, c, v)``
                         right after each successful persistence.
    """

    def __init__(
        self,
        *,
        timeframe: str = "1min",
        bucket_seconds: int = 60,
        on_candle: Any | None = None,
    ) -> None:
        if bucket_seconds <= 0:
            raise ValueError("bucket_seconds must be positive")
        self._timeframe = timeframe
        self._bucket_seconds = bucket_seconds
        self._on_candle = on_candle
        self._states: dict[int, _TokenState] = {}
        self._lock = threading.Lock()

    # ------------------------------------------------------------------
    def handle_quote(self, quote: Any) -> None:
        """Ingest one parsed ``Quote`` (callback target for the tick manager)."""
        token = self._token_from_symbol(quote.symbol)
        if token is None or quote.ltp is None:
            return

        tick_at = quote.tick_at
        if tick_at.tzinfo is None:
            tick_at = tick_at.replace(tzinfo=timezone.utc)
        bucket_start = self._floor_to_bucket(tick_at.astimezone(timezone.utc))

        with self._lock:
            state = self._states.setdefault(token, _TokenState())
            closed: _Bucket | None = None

            volume_delta = 0
            cum_volume = quote.volume
            if cum_volume is not None:
                if state.last_cum_volume is not None:
                    volume_delta = max(0, cum_volume - state.last_cum_volume)
                state.last_cum_volume = cum_volume
            # A None cumulative counter (quote.volume is None) contributes no
            # volume but still updates OHLC.

            current = state.bucket
            if current is None:
                state.bucket = _Bucket(started_at=bucket_start)
                current = state.bucket
            elif bucket_start > current.started_at:
                closed = current
                current = state.bucket = _Bucket(started_at=bucket_start)

            current.add(quote.ltp, volume_delta)

        if closed is not None:
            self._persist(token, closed)

    def flush(self) -> int:
        """Persist all in-flight buckets (graceful-shutdown hook)."""
        with self._lock:
            pending = [
                (token, state.bucket)
                for token, state in self._states.items()
                if state.bucket is not None
            ]
            self._states.clear()
        persisted = 0
        for token, bucket in pending:
            if bucket.open_ is not None:
                self._persist(token, bucket)
                persisted += 1
        return persisted

    @property
    def in_flight(self) -> int:
        return sum(1 for s in self._states.values() if s.bucket is not None)

    # ------------------------------------------------------------------
    @staticmethod
    def _token_from_symbol(symbol: str) -> int | None:
        # ZerodhaTickerAdapter emits ``token:<instrument_token>`` because it
        # has no DB access; resolve it here where Django ORM is available.
        prefix = "token:"
        if symbol.startswith(prefix):
            raw = symbol[len(prefix):]
            try:
                return int(raw)
            except ValueError:
                logger.warning("tick_aggregator_bad_token", extra={"symbol": symbol})
        return None

    def _floor_to_bucket(self, ts: datetime) -> datetime:
        seconds = self._bucket_seconds
        epoch_floor = ts.timestamp() // seconds * seconds
        return datetime.fromtimestamp(epoch_floor, tz=timezone.utc)

    def _persist(self, token: int, bucket: _Bucket) -> None:
        if bucket.open_ is None or bucket.close is None:
            return
        from apps.market_data.infrastructure.repositories import CandleRepository

        try:
            CandleRepository().upsert(
                instrument_token=token,
                timeframe=self._timeframe,
                timestamp=bucket.started_at,
                open=bucket.open_,
                high=bucket.high,
                low=bucket.low,
                close=bucket.close,
                volume=bucket.volume,
            )
        except Exception:
            logger.exception(
                "tick_aggregator_upsert_failed",
                extra={"instrument_token": token, "timestamp": bucket.started_at.isoformat()},
            )
            return

        logger.info(
            "tick_aggregator_candle_persisted",
            extra={
                "instrument_token": token,
                "timeframe": self._timeframe,
                "timestamp": bucket.started_at.isoformat(),
                "volume": bucket.volume,
            },
        )
        if self._on_candle is not None:
            try:
                self._on_candle(token, bucket.started_at)
            except Exception:
                logger.exception(
                    "tick_aggregator_on_candle_failed",
                    extra={"instrument_token": token},
                )
