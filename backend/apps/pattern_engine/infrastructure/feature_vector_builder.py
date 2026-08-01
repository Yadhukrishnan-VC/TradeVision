from __future__ import annotations

import logging
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation

from apps.market_data.infrastructure.repositories import (
    CandleRepository,
    InstrumentRepository,
)
from apps.pattern_engine.domain.value_objects import FeatureVector
from apps.technical_analysis.infrastructure.repositories import TASnapshotRepository
from core.events.event_types import MarketTrend

logger = logging.getLogger(__name__)

SIX_DP = Decimal("0.000001")


def safe_decimal(value) -> Decimal | None:
    """Best-effort conversion of an arbitrary value to Decimal (or None)."""
    if value is None:
        return None
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError, ArithmeticError):
        return None


_TA_KEYS: dict[str, tuple[str, ...]] = {
    "rsi_14": ("rsi_14", "rsi"),
    "macd_histogram": ("macd_histogram", "macdHist", "macd_hist"),
    "bb_upper": ("bb_upper", "bbUpper"),
    "bb_lower": ("bb_lower", "bbLower"),
    "trend": ("trend", "trend_direction", "market_trend"),
}


def _indicators_get(indicators: dict, key: str):
    for candidate in _TA_KEYS[key]:
        if candidate in indicators:
            return indicators[candidate]
    for candidate, raw in indicators.items():
        if str(candidate).strip().lower() == key:
            return raw
    return None


def _trend_from(value) -> MarketTrend | None:
    if value is None:
        return None
    text = str(value).upper()
    for candidate in MarketTrend:
        if candidate.value in text:
            return candidate
    return None


def _date_of(value: datetime | date) -> date:
    if isinstance(value, datetime):
        return value.date()
    return value


def _window_start(as_of: datetime | date, lookback_days: int) -> datetime:
    """Start of the lookback window (UTC, inclusive of the target day)."""
    if isinstance(as_of, date) and not isinstance(as_of, datetime):
        as_of = datetime.combine(as_of, datetime.min.time(), tzinfo=timezone.utc)
    return as_of - timedelta(days=lookback_days)


def build_historical_feature_vector(
    symbol: str,
    as_of: datetime | date,
    *,
    candle_repo: CandleRepository | None = None,
    ta_repo: TASnapshotRepository | None = None,
    instrument_repo: InstrumentRepository | None = None,
    lookback_days: int = 120,
) -> FeatureVector | None:
    """Build a ``FeatureVector`` for a single historical session.

    Uses the same feature definitions as
    ``apps.pattern_engine.domain.similarity.build_feature_vector`` but
    derives them from OHLCV candles and (optionally) Technical Analysis
    snapshots instead of a live IntelligencePacket. Options, macro, and
    breadth features are ``None`` for historical sessions unless snapshots
    provide them — the similarity scorer excludes missing groups.

    Args:
        symbol:        Trading symbol (case-insensitive).
        as_of:         Session date or datetime (UTC).
        candle_repo:   Injectable for tests; defaults to ``CandleRepository``.
        ta_repo:       Injectable for tests; defaults to ``TASnapshotRepository``.
        instrument_repo: Injectable for tests; defaults to ``InstrumentRepository``.
        lookback_days: Calendar-day lookback used to compute the 20-session
                       average volume.

    Returns:
        A populated ``FeatureVector``, or ``None`` when fewer than two candles
        exist before ``as_of`` (change/gap cannot be computed).
    """
    from apps.common.domain.value_objects import Symbol

    instrument_repo = instrument_repo or InstrumentRepository()
    candle_repo = candle_repo or CandleRepository()
    ta_repo = ta_repo or TASnapshotRepository()

    instrument = instrument_repo.find_by_symbol(
        Symbol(exchange="NSE", tradingsymbol=symbol.upper())
    )
    if instrument is None:
        logger.warning(
            "pe_no_instrument",
            extra={"symbol": symbol.upper()},
        )
        return None

    as_of_dt = (
        as_of
        if isinstance(as_of, datetime)
        else datetime.combine(as_of, datetime.min.time(), tzinfo=timezone.utc)
    )
    if as_of_dt.tzinfo is None:
        as_of_dt = as_of_dt.replace(tzinfo=timezone.utc)

    end = as_of_dt + timedelta(days=1)
    candles = candle_repo.find_range(
        instrument.instrument_token,
        "1D",
        _window_start(as_of_dt, lookback_days),
        end,
    )

    if len(candles) < 2:
        return None

    session_candles = [
        c for c in candles if _date_of(c.timestamp) <= _date_of(as_of_dt)
    ]
    if len(session_candles) < 2:
        return None

    session = session_candles[-1]
    prev = session_candles[-2]

    prev_close = prev.close
    if prev_close == 0:
        return None

    change_pct = ((session.close - prev_close) / prev_close * Decimal(100)).quantize(
        SIX_DP
    )
    gap_pct = ((session.open - prev_close) / prev_close * Decimal(100)).quantize(SIX_DP)

    window = session_candles[:-1]
    if window:
        avg_volume = sum(c.volume for c in window) / Decimal(len(window))
    else:
        avg_volume = Decimal(session.volume) if session.volume else Decimal(0)

    volume_ratio = (
        Decimal(session.volume) / avg_volume if avg_volume > 0 else Decimal(0)
    ).quantize(SIX_DP)

    # Technical indicators — tolerant key lookup; absent for historical
    # sessions without a matching TA snapshot.
    indicators: dict = {}
    try:
        snapshots = ta_repo.find_by_symbol(symbol, limit=100)
    except Exception:
        snapshots = []

    for snapshot in snapshots:
        if _date_of(snapshot.snapshot_timestamp) == _date_of(as_of_dt):
            indicators = snapshot.indicators or {}
            break

    rsi_14 = safe_decimal(_indicators_get(indicators, "rsi_14"))
    macd_hist = safe_decimal(_indicators_get(indicators, "macd_histogram"))
    bb_upper = safe_decimal(_indicators_get(indicators, "bb_upper"))
    bb_lower = safe_decimal(_indicators_get(indicators, "bb_lower"))
    trend = _trend_from(_indicators_get(indicators, "trend"))

    bb_position = None
    if bb_upper is not None and bb_lower is not None and bb_upper > bb_lower:
        bb_position = ((session.close - bb_lower) / (bb_upper - bb_lower)).quantize(
            SIX_DP
        )

    return FeatureVector(
        symbol=symbol.upper(),
        as_of=as_of_dt,
        price_change_pct=change_pct,
        gap_pct=gap_pct,
        volume_ratio=volume_ratio,
        rsi_14=rsi_14,
        macd_histogram=macd_hist,
        bb_position=bb_position,
        trend=trend,
        pcr=None,
        oi_change_direction=None,
        nifty_change_pct=Decimal(0),
        crude_oil_pct=None,
        fii_flow_direction=None,
        sector_trend_direction=None,
        advance_decline_ratio=None,
    )


def compute_outcome(
    symbol: str,
    as_of: datetime | date,
    *,
    candle_repo: CandleRepository | None = None,
    instrument_repo: InstrumentRepository | None = None,
) -> tuple[Decimal | None, int]:
    """Return ``(subsequent_price_change_pct, window_hours)`` for a session.

    The outcome is the % change of the next trading session after ``as_of``
    (24-hour window by default). Returns ``(None, 24)`` when no next session
    exists.
    """
    from apps.common.domain.value_objects import Symbol

    instrument_repo = instrument_repo or InstrumentRepository()
    candle_repo = candle_repo or CandleRepository()

    instrument = instrument_repo.find_by_symbol(
        Symbol(exchange="NSE", tradingsymbol=symbol.upper())
    )
    if instrument is None:
        return None, 24

    as_of_dt = (
        as_of
        if isinstance(as_of, datetime)
        else datetime.combine(as_of, datetime.min.time(), tzinfo=timezone.utc)
    )
    if as_of_dt.tzinfo is None:
        as_of_dt = as_of_dt.replace(tzinfo=timezone.utc)

    candles = candle_repo.find_range(
        instrument.instrument_token,
        "1D",
        _window_start(as_of_dt, 40),
        as_of_dt + timedelta(days=2),
    )
    upcoming = [c for c in candles if c.timestamp > as_of_dt]
    if not upcoming:
        return None, 24

    nxt = upcoming[0]

    # prev session close is the last candle <= as_of_dt
    past = [c for c in candles if c.timestamp <= as_of_dt]
    prev_close = past[-1].close if past else None
    if prev_close is None or prev_close == 0:
        return None, 24

    change_pct = ((nxt.close - prev_close) / prev_close * Decimal(100)).quantize(SIX_DP)
    return change_pct, 24


__all__ = ["build_historical_feature_vector", "compute_outcome"]
