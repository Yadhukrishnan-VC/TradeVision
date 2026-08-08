"""
Candle ⟷ Technical Analysis bridge (Batch M4).

A small, synchronous adapter that turns freshly-persisted REST-polled
``Candle`` rows into the exact TradingView-style payload shape the existing
``TechnicalAnalysisIngestionService.ingest()`` consumes, and feeds that seam.

This is the ONLY new TA consumption path this batch introduces. It deliberately
does NOT compute indicators: the payload carries only OHLCV + prev-close-derived
``change_pct`` so that REST-only rules (``price_movement_v1``, ``volume_spike_v1``)
can fire while indicator-dependent rules fail closed (missing data → None).
"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timedelta
from decimal import ROUND_HALF_UP, Decimal
from typing import Any

from apps.common.domain.value_objects import IdempotencyKey
from apps.eventbus.infrastructure.event_bus_factory import get_event_bus
from apps.market_data.domain.entities import Candle
from apps.market_data.infrastructure.repositories import (
    CandleRepository,
    InstrumentRepository,
)
from apps.technical_analysis.application.services import TechnicalAnalysisIngestionService
from apps.technical_analysis.infrastructure.repositories import TASnapshotRepository
from core.config import config
from core.redis_client import get_redis_client
from core.utils import get_now, to_utc

logger = logging.getLogger(__name__)

_REDIS_KEY_PREFIX = "tradevision:market_data:poll_ta"

_CHANGE_PCT_QUANT = Decimal("0.0001")


class CandleToTechnicalAnalysisBridge:
    """Adapter from persisted candles to the TA ingestion seam.

    Responsibilities:
        1. Compute a TradingView-shaped payload for one candle.
        2. Reject stale candles (older than the staleness window). Build
           Redis marker per (instrument_token, timeframe) -> last-ingested
           candle timestamp so a genuinely new candle is ingested exactly once.
        3. Publish the candle through ``TechnicalAnalysisIngestionService``
           (unchanged), then update the marker only after a successful ingest.

    The bridge is intentionally context-free at the call boundary: the polling
    task passes an explicit timestamp (the newest backfilled candle), and the
    bridge looks the candle up from the already-persisted rows.
    """

    def __init__(
        self,
        instrument_repo: InstrumentRepository | None = None,
        candle_repo: CandleRepository | None = None,
        ingestion_service: TechnicalAnalysisIngestionService | None = None,
        redis_client: Any | None = None,
        staleness_seconds: int | None = None,
    ) -> None:
        self._instrument_repo = instrument_repo or InstrumentRepository()
        self._candle_repo = candle_repo or CandleRepository()
        self._redis = redis_client or get_redis_client()
        self._staleness_seconds = staleness_seconds or config.market_data_poll_staleness_seconds
        self._ingestion_service = ingestion_service or TechnicalAnalysisIngestionService(
            repository=TASnapshotRepository(),
            event_bus=get_event_bus(),
        )

    # ------------------------------------------------------------------
    # Public API — driven by the polling task
    # ------------------------------------------------------------------

    def should_ingest(self, instrument_token: int, timeframe: str, candle_timestamp: datetime) -> bool:
        """Return ``True`` only for a market-fresh, not-yet-ingested candle.

        Stale candles (older than the freshness window relative to now) and
        duplicates (timestamp already ingested) are logged and skipped — never
        raised. This is the bridge's staleness guard + exactly-once marker.
        """
        now = to_utc(get_now())
        candle_timestamp = to_utc(candle_timestamp)

        age = now - candle_timestamp
        if age > timedelta(seconds=self._staleness_seconds):
            logger.info(
                "candle_ta_poll_stale_skipped",
                extra={
                    "instrument_token": instrument_token,
                    "timeframe": timeframe,
                    "candle_timestamp_utc": candle_timestamp.isoformat(),
                    "age_seconds": int(age.total_seconds()),
                    "staleness_seconds": self._staleness_seconds,
                },
            )
            return False

        last_seen = self._last_ingested_timestamp(instrument_token, timeframe)
        if last_seen is not None and candle_timestamp <= last_seen:
            logger.info(
                "candle_ta_poll_duplicate_skipped",
                extra={
                    "instrument_token": instrument_token,
                    "timeframe": timeframe,
                    "candle_timestamp_utc": candle_timestamp.isoformat(),
                },
            )
            return False

        return True

    def mark_ingested(self, instrument_token: int, timeframe: str, candle_timestamp: datetime) -> None:
        """Persist the marker that ``candle_timestamp`` was reacted to.

        Timestamps are stored as UTC ISO-8601 strings so keep the marker
        comparable across Redis string boundaries.
        """
        key = self._marker_key(instrument_token, timeframe)
        self._redis.set(key, to_utc(candle_timestamp).isoformat())

    # ------------------------------------------------------------------
    # Payload construction + publish (with nothing-but-OHLCV indicators)
    # ------------------------------------------------------------------

    def build_payload_for_candle(self, candle: Candle) -> dict[str, Any]:
        """Build the TA ingestion payload from one persisted candle.

        Returns a dict in the shape ``TechnicalAnalysisIngestionService``
        accepts: ticker/close required, plus OHLCV + prev_close/change_pct.
        No indicator keys are emitted — indicator-dependent rules fail safe.
        """
        instrument = self._instrument_repo.find_by_token(candle.instrument_token)
        if instrument is None:
            raise ValueError(
                f"No instrument for token {candle.instrument_token}. "
                "Refusing to ingest candles for an unknown instrument."
            )

        prev_close, change_pct = self._prev_close_and_change(candle)

        payload: dict[str, Any] = {
            "ticker": instrument.tradingsymbol,
            "exchange": instrument.exchange,
            "timeframe": candle.timeframe,
            "open": str(candle.open),
            "high": str(candle.high),
            "low": str(candle.low),
            "close": str(candle.close),
            "volume": int(candle.volume),
            "time": int(to_utc(candle.timestamp).timestamp() * 1000),
        }
        if prev_close is not None:
            payload["prev_close"] = str(prev_close)
        if change_pct is not None:
            payload["change_pct"] = str(change_pct)
        return payload

    def ingest_fresh_candle(self, instrument_token: int, timeframe: str, candle_timestamp: datetime) -> Candle | None:
        """Ingest one freshly-persisted candle through the TA seam.

        Returns the ``Candle`` when it was published, ``None`` when
        stale/duplicate (skip). Raises only when the ingestion service itself
        fails (poor) — the polling task surfaces that per-symbol.
        """
        if not self.should_ingest(instrument_token, timeframe, candle_timestamp):
            return None

        candle = self._candle_for_timestamp(instrument_token, timeframe, candle_timestamp)
        if candle is None:
            logger.warning(
                "candle_ta_poll_not_found",
                extra={
                    "instrument_token": instrument_token,
                    "timeframe": timeframe,
                    "candle_timestamp_utc": to_utc(candle_timestamp).isoformat(),
                },
            )
            return None

        payload = self.build_payload_for_candle(candle)
        correlation_id = self._deterministic_correlation(candle)

        try:
            self._ingestion_service.ingest(payload, correlation_id=correlation_id)
        except Exception:
            logger.exception(
                "candle_ta_poll_ingest_failed",
                extra={
                    "instrument_token": instrument_token,
                    "timeframe": timeframe,
                    "candle_timestamp_utc": to_utc(candle_timestamp).isoformat(),
                },
            )
            raise

        self.mark_ingested(instrument_token, timeframe, candle.timestamp)
        logger.info(
            "candle_ta_poll_ingested",
            extra={
                "instrument_token": instrument_token,
                "timeframe": timeframe,
                "candle_timestamp_utc": to_utc(candle.timestamp).isoformat(),
                "correlation_id": str(correlation_id),
            },
        )
        return candle

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _candle_for_timestamp(self, instrument_token: int, timeframe: str, ts: datetime) -> Candle | None:
        ts_utc = to_utc(ts)
        candles = self._candle_repo.find_range(instrument_token, timeframe, ts_utc, ts_utc)
        return candles[0] if candles else None

    def _prev_close_and_change(self, candle: Candle) -> tuple[Decimal | None, Decimal | None]:
        """Return ``(prev_close, change_pct)`` derived from persisted candles.

        ``prev_close`` is the close of the candle immediately preceding the
        target candle in the same (symbol, timeframe) series. ``change_pct``
        is the target candle's intra-bar percentage move against that close,
        precision-capped to 4 decimals so it survives JSON serialization.
        """
        context = self._candle_repo.find_latest(candle.instrument_token, candle.timeframe, limit=20)
        prev_close: Decimal | None = None
        change_pct: Decimal | None = None
        for idx, other in enumerate(context):
            if to_utc(other.timestamp) == to_utc(candle.timestamp):
                if idx > 0:
                    prev_close = context[idx - 1].close
                break
        if prev_close is not None and prev_close != Decimal("0"):
            change_pct = ((candle.close - prev_close) / prev_close) * Decimal("100")
            change_pct = change_pct.quantize(_CHANGE_PCT_QUANT, rounding=ROUND_HALF_UP)
        return prev_close, change_pct

    def _last_ingested_timestamp(self, instrument_token: int, timeframe: str) -> datetime | None:
        raw = self._redis.get(self._marker_key(instrument_token, timeframe))
        if not raw:
            return None
        try:
            return to_utc(datetime.fromisoformat(raw))
        except (ValueError, TypeError):
            logger.warning(
                "candle_ta_poll_invalid_marker",
                extra={"instrument_token": instrument_token, "timeframe": timeframe, "raw": str(raw)},
            )
            return None

    @staticmethod
    def _marker_key(instrument_token: int, timeframe: str) -> str:
        return f"{_REDIS_KEY_PREFIX}:{instrument_token}:{timeframe}"

    @staticmethod
    def _deterministic_correlation(candle: Candle) -> uuid.UUID:
        return uuid.UUID(
            hex=IdempotencyKey.generate(
                "market-data-rest-poll",
                str(candle.instrument_token),
                candle.timeframe,
                candle.timestamp.isoformat(),
            ).value[:32]
        )


_bridge_instance: CandleToTechnicalAnalysisBridge | None = None


def get_candle_ta_bridge() -> CandleToTechnicalAnalysisBridge:
    """Return a process-wide ``CandleToTechnicalAnalysisBridge`` singleton."""
    global _bridge_instance
    if _bridge_instance is None:
        _bridge_instance = CandleToTechnicalAnalysisBridge()
    return _bridge_instance


def reset_candle_ta_bridge() -> None:
    """Reset the singleton (primarily for testing)."""
    global _bridge_instance
    _bridge_instance = None