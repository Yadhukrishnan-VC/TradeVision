"""
Candle ⟷ Technical Analysis bridge (Batch M4/M5).

A small, synchronous adapter that turns freshly-persisted REST-polled
``Candle`` rows into the exact TradingView-style payload shape the existing
``TechnicalAnalysisIngestionService.ingest()`` consumes, and feeds that seam.

This is the ONLY new TA consumption path. The payload carries OHLCV +
prev-close-derived ``change_pct`` plus, when enough history exists, five
deterministic indicators computed from the same persisted candles — ``vwap``
(session-sliced), ``ema_20``, ``atr_14``, ``bb_upper`` (sample-σ Bollinger) and
``rsi_14`` (Wilder) — so that indicator-dependent rules can fire on real
market data. With insufficient history those keys are simply omitted (never
zero-filled), so the rules fail closed exactly as they did in M4.
"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timedelta
from decimal import ROUND_HALF_UP, Decimal
from typing import Any

from apps.common.domain.value_objects import IdempotencyKey
from apps.eventbus.infrastructure.event_bus_factory import get_event_bus
from apps.market_data.application.session_facts_service import SessionFactsService
from apps.market_data.domain.entities import Candle
from apps.market_data.domain.value_objects import Timeframe
from apps.market_data.infrastructure.repositories import (
    CandleRepository,
    InstrumentRepository,
)
from apps.technical_analysis.application.services import TechnicalAnalysisIngestionService
from apps.technical_analysis.domain.indicators import (
    compute_atr,
    compute_bollinger_upper,
    compute_ema,
    compute_rsi,
    compute_supertrend,
    compute_vwap,
)
from apps.technical_analysis.infrastructure.repositories import TASnapshotRepository
from core.config import config
from core.redis_client import get_redis_client
from core.utils import get_now, to_utc

logger = logging.getLogger(__name__)

_REDIS_KEY_PREFIX = "tradevision:market_data:poll_ta"

_CHANGE_PCT_QUANT = Decimal("0.0001")

# M5 warm-up gates. EMA20 is deliberately stricter (approved Decision C: the
# value is only decision-grade once 3x the period of candles exist, avoiding
# seed bias after a cold start). ATR/BB are well-defined at their fixed window.
_MIN_CANDLES_EMA20 = 60
_MIN_CANDLES_ATR14 = 15
_MIN_CANDLES_BB = 20

# TA-2: RSI14 needs 14 price changes + a seed close (period + 1), the same
# warm-up contract as ATR14.
_MIN_CANDLES_RSI14 = 15

# Supertrend (10,2) needs 10 true ranges for the Wilder ATR seed plus one
# prior close for the first band transition; a modest cushion keeps the
# band stable before it is decision-grade.
_MIN_CANDLES_SUPERTREND = 21

# Daily candles are stamped at 00:00 UTC (05:30 IST — before the NSE session).
# The analysis snapshot time is normalised into the session (07:00 UTC = 12:30
# IST, mid-session) so downstream consumers that gate on market hours (e.g. the
# risk engine's MarketSessionCheck) treat a completed daily bar as in-session.
_DAILY_BAR_SNAPSHOT_OFFSET = timedelta(hours=7)


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
        session_facts: SessionFactsService | None = None,
        ta_repo: TASnapshotRepository | None = None,
    ) -> None:
        self._instrument_repo = instrument_repo or InstrumentRepository()
        self._candle_repo = candle_repo or CandleRepository()
        self._session_facts = session_facts or SessionFactsService(candle_repo=self._candle_repo)
        self._redis = redis_client or get_redis_client()
        self._staleness_seconds = staleness_seconds or config.market_data_poll_staleness_seconds
        self._ta_repo = ta_repo or TASnapshotRepository()
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

    def build_payload_for_candle(
        self,
        candle: Candle,
        up_to: datetime | None = None,
    ) -> dict[str, Any]:
        """Build the TA ingestion payload from one persisted candle.

        Returns a dict in the shape ``TechnicalAnalysisIngestionService``
        accepts: ticker/close required, plus OHLCV + prev_close/change_pct AND,
        when sufficient persisted history exists, indicator keys (``vwap``,
        ``ema_20``, ``atr_14``, ``bb_upper``, ``rsi_14``). Insufficient history
        omits the corresponding keys (never ``0``, never fabricated) so
        indicator rules fail closed.

        ``up_to`` (optional) temporally anchors every history query to
        ``<= up_to``, so each candle's indicators only see genuinely earlier
        history — used by the historical backfill where the whole range is
        already persisted. The live polling path omits it and is unchanged.
        """
        instrument = self._instrument_repo.find_by_token(candle.instrument_token)
        if instrument is None:
            raise ValueError(
                f"No instrument for token {candle.instrument_token}. "
                "Refusing to ingest candles for an unknown instrument."
            )

        prev_close, change_pct = self._prev_close_and_change(candle, up_to=up_to)
        indicators = self._compute_indicators(candle, up_to=up_to)

        snapshot_ts = to_utc(candle.timestamp)
        if candle.timeframe == Timeframe.DAY_1:
            snapshot_ts = snapshot_ts + _DAILY_BAR_SNAPSHOT_OFFSET

        payload: dict[str, Any] = {
            "ticker": instrument.tradingsymbol,
            "exchange": instrument.exchange,
            "timeframe": candle.timeframe,
            "open": str(candle.open),
            "high": str(candle.high),
            "low": str(candle.low),
            "close": str(candle.close),
            "volume": int(candle.volume),
            "time": int(snapshot_ts.timestamp() * 1000),
        }
        if prev_close is not None:
            payload["prev_close"] = str(prev_close)
        if change_pct is not None:
            payload["change_pct"] = str(change_pct)
        payload.update(indicators)
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
    # Historical TA backfill (Batch HISTORICAL-TA-BACKFILL-1)
    # ------------------------------------------------------------------

    def backfill_ta_from_candles(
        self,
        instrument_token: int,
        timeframe: str,
        from_timestamp: datetime,
        to_timestamp: datetime,
    ) -> int:
        """Ingest already-persisted historical candles into ``TASnapshot``.

        Historical replay is definitionally not "fresh", so this entry point
        deliberately bypasses :meth:`should_ingest`'s "now"-relative staleness
        gate while reusing the *unchanged* payload builder and ingestion seam:
        each candle goes through :meth:`build_payload_for_candle` (same
        indicator computation, same warm-up gating, same never-zero-filled
        key-omission) then ``TechnicalAnalysisIngestionService.ingest``.

        Candles are processed strictly oldest-to-newest (``CandleRepository``
        orders the range chronologically) and each candle's payload is built
        with a temporal bound (``up_to=candle.timestamp``) so its indicator
        window (``_indicator_series`` reads "most recent N candles") only ever
        sees genuinely earlier history. Because ``HistoricalSyncService``
        persists the whole range up front, this bound — not loop order alone —
        is what guarantees causality for the historical path.

        Idempotency: ``TASnapshot`` has no DB uniqueness on
        ``(symbol, snapshot_timestamp)``, so a pre-existing snapshot for a
        candle is detected up front (one range query) and skipped — re-running
        a range never duplicates rows nor re-publishes
        ``TechnicalAnalysisCompleted`` events. A single failed ``ingest()`` is
        logged and isolated (does not abort the rest of the range), mirroring
        the "count persisted" pattern of ``HistoricalSyncService``.

        Returns the number of candles ingested.
        """
        instrument = self._instrument_repo.find_by_token(instrument_token)
        if instrument is None:
            raise ValueError(
                f"No instrument for token {instrument_token}. "
                "Refusing to backfill TA for an unknown instrument."
            )

        candles = self._candle_repo.find_range(
            instrument_token, timeframe, from_timestamp, to_timestamp
        )
        symbol = instrument.tradingsymbol.upper()
        existing = {
            to_utc(s.snapshot_timestamp).timestamp()
            for s in self._ta_repo.find_in_range(
                symbol, from_timestamp, to_timestamp, timeframe=timeframe
            )
        }

        created = 0
        failures = 0
        for candle in candles:
            candle_ts = to_utc(candle.timestamp)
            if candle_ts.timestamp() in existing:
                logger.info(
                    "historical_ta_backfill_skip_existing",
                    extra={
                        "instrument_token": instrument_token,
                        "timeframe": timeframe,
                        "candle_timestamp_utc": candle_ts.isoformat(),
                    },
                )
                continue

            try:
                payload = self.build_payload_for_candle(candle, up_to=candle.timestamp)
                correlation_id = self._deterministic_correlation(candle)
                self._ingestion_service.ingest(payload, correlation_id=correlation_id)
                created += 1
            except Exception:
                failures += 1
                logger.exception(
                    "historical_ta_backfill_candle_failed",
                    extra={
                        "instrument_token": instrument_token,
                        "timeframe": timeframe,
                        "candle_timestamp_utc": candle_ts.isoformat(),
                    },
                )

        logger.info(
            "historical_ta_backfill_completed",
            extra={
                "instrument_token": instrument_token,
                "timeframe": timeframe,
                "from_timestamp_utc": to_utc(from_timestamp).isoformat(),
                "to_timestamp_utc": to_utc(to_timestamp).isoformat(),
                "candles_processed": len(candles),
                "snapshots_created": created,
                "failures": failures,
            },
        )
        return created

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _candle_for_timestamp(self, instrument_token: int, timeframe: str, ts: datetime) -> Candle | None:
        ts_utc = to_utc(ts)
        candles = self._candle_repo.find_range(instrument_token, timeframe, ts_utc, ts_utc)
        return candles[0] if candles else None

    def _prev_close_and_change(
        self, candle: Candle, up_to: datetime | None = None
    ) -> tuple[Decimal | None, Decimal | None]:
        context = self._candle_repo.find_latest(
            candle.instrument_token, candle.timeframe, limit=20, up_to=up_to
        )
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

    def _compute_indicators(
        self, candle: Candle, up_to: datetime | None = None
    ) -> dict[str, str]:
        """Compute M5 indicator values for *candle* from persisted history.

        Only keys with a decision-grade value are emitted (warm-up simply
        omits the key — never zero-filled, never fabricated). Values are
        stringified so they survive JSON serialization exactly like the
        existing ``prev_close``/``change_pct`` fields.

        The shared 60-candle fetch covers all fixed-window indicators;
        VWAP is sliced separately from the session-open boundary derived via
        ``SessionFactsService``. ``up_to`` (optional) anchors every history
        query to ``<= up_to`` (historical backfill); the live path omits it.
        """
        history = self._indicator_series(candle, up_to=up_to)
        vwap = self._compute_vwap(candle, up_to=up_to)

        indicators: dict[str, Any] = {}
        if len(history) >= _MIN_CANDLES_EMA20:
            ema_20 = compute_ema(history, period=20)
            if ema_20 is not None:
                indicators["ema_20"] = str(ema_20)
        if len(history) >= _MIN_CANDLES_ATR14:
            atr_14 = compute_atr(history, period=14)
            if atr_14 is not None:
                indicators["atr_14"] = str(atr_14)
        if len(history) >= _MIN_CANDLES_RSI14:
            rsi_14 = compute_rsi(history, period=14)
            if rsi_14 is not None:
                indicators["rsi_14"] = str(rsi_14)
        if len(history) >= _MIN_CANDLES_BB:
            bb_upper = compute_bollinger_upper(history, period=20)
            if bb_upper is not None:
                indicators["bb_upper"] = str(bb_upper)
        if len(history) >= _MIN_CANDLES_SUPERTREND:
            supertrend = compute_supertrend(history, period=10, multiplier=Decimal("2"))
            if supertrend is not None:
                value, direction = supertrend
                indicators["supertrend_value"] = str(value)
                indicators["supertrend_direction"] = direction
        if vwap is not None:
            indicators["vwap"] = str(vwap)
        return indicators

    def _indicator_series(
        self, candle: Candle, up_to: datetime | None = None
    ) -> list[Candle]:
        """Most recent 60 candles for the shared indicator window.

        With ``up_to`` set, the window is the most recent 60 candles at or
        before ``up_to`` — the causal bound the historical backfill needs.
        """
        return self._candle_repo.find_latest(
            candle.instrument_token, candle.timeframe, limit=_MIN_CANDLES_EMA20, up_to=up_to
        )

    def _compute_vwap(
        self, candle: Candle, up_to: datetime | None = None
    ) -> Decimal | None:
        """VWAP from the current session's candles (session-sliced).

        Uses ``SessionFactsService`` to find the session boundary (09:15 IST
        opening candle) for the candle's trading day, then scans the same
        timeframe from that boundary up to and including *candle*. When the
        session open cannot be determined, VWAP is unavailable (``None``).
        ``up_to`` (optional) anchors the session slice to ``<= up_to``.
        """
        opening = self._session_facts.get_opening_15m_candle(
            candle.instrument_token, to_utc(candle.timestamp)
        )
        if opening is None:
            return None
        session_open_utc = to_utc(opening.timestamp)
        end_ts = to_utc(candle.timestamp if up_to is None else up_to)
        session_candles = self._candle_repo.find_range(
            candle.instrument_token,
            candle.timeframe,
            session_open_utc,
            end_ts,
        )
        return compute_vwap(session_candles)

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