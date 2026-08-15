"""
TradeVision AI — Core event and intelligence contract types.

These frozen dataclasses are the central data contracts shared across all
modules. No Django ORM or external library imports are permitted here —
this module must remain importable in isolation for testing and tooling.

Design rules for types in this module:
  - All dataclasses are frozen (immutable after construction).
  - Financial values use Decimal, never float.
  - All datetime fields must be timezone-aware; __post_init__ enforces this.
  - Optional context blocks use ``| None = None`` for clear optionality.
  - Tuple is used instead of list for immutable sequences of items.
"""

import uuid
from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from enum import Enum
from typing import Any


# ---------------------------------------------------------------------------
# Enumerations
# ---------------------------------------------------------------------------


class CircuitStatus(str, Enum):
    """NSE price band / circuit breaker status for a stock."""

    NORMAL = "NORMAL"
    UPPER_CIRCUIT = "UPPER_CIRCUIT"
    LOWER_CIRCUIT = "LOWER_CIRCUIT"


class MarketTrend(str, Enum):
    """Directional trend classification from technical analysis."""

    UPTREND = "UPTREND"
    DOWNTREND = "DOWNTREND"
    SIDEWAYS = "SIDEWAYS"


class AggregateSentiment(str, Enum):
    """Aggregate news sentiment for a symbol."""

    POSITIVE = "POSITIVE"
    NEGATIVE = "NEGATIVE"
    NEUTRAL = "NEUTRAL"
    MIXED = "MIXED"


class MaterialityLevel(str, Enum):
    """Assessed importance of a news item or corporate announcement."""

    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


class EventType(str, Enum):
    """Classification of the detected market event that triggered an AI call."""

    PRICE_MOVEMENT = "price_movement"
    VOLUME_SPIKE = "volume_spike"
    BREAKOUT = "breakout"
    BREAKDOWN = "breakdown"
    CIRCUIT_BREAKER = "circuit_breaker"
    GAP_MOVEMENT = "gap_movement"
    ANNOUNCEMENT = "announcement"
    EARNINGS = "earnings"
    INSTITUTIONAL_ACTIVITY = "institutional_activity"
    MACRO_EVENT = "macro_event"
    MULTI_EVENT = "multi_event"


# ---------------------------------------------------------------------------
# Context sub-blocks — components of IntelligencePacket
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class PriceContext:
    """Current price and volume snapshot for a symbol."""

    current_price: Decimal
    open_price: Decimal
    high: Decimal
    low: Decimal
    volume: int
    avg_volume_20d: int
    circuit_status: CircuitStatus
    prev_close: Decimal | None = None
    change_pct: Decimal | None = None
    avg_volume_10d: int | None = None
    """Average daily volume over the trailing 10 sessions (0 or None when
    unavailable). Populated from persisted market-data candles at packet
    assembly; deterministic setups use it for volume-ratio conditions."""
    avg_volume_5d: int | None = None
    """Average daily volume over the trailing 5 sessions (None when fewer
    than 5 trailing day-candle sessions exist). Populated from persisted
    market-data candles at packet assembly via ``SessionFactsService``;
    follows the same optional-int convention as ``avg_volume_10d``."""


@dataclass(frozen=True)
class TechnicalContext:
    """Computed technical indicator values. All fields are optional because
    indicators require a minimum history window that may not be available."""

    trend: MarketTrend = MarketTrend.SIDEWAYS
    rsi_14: Decimal | None = None
    macd: Decimal | None = None
    macd_signal: Decimal | None = None
    macd_histogram: Decimal | None = None
    bb_upper: Decimal | None = None
    bb_lower: Decimal | None = None
    bb_width: Decimal | None = None
    vwap: Decimal | None = None
    atr_14: Decimal | None = None
    ema_20: Decimal | None = None
    ema_50: Decimal | None = None
    ema_200: Decimal | None = None
    support_levels: tuple[Decimal, ...] = ()
    resistance_levels: tuple[Decimal, ...] = ()
    supertrend_value: Decimal | None = None
    """Supertrend(10, 2) value as supplied by the Pine alert payload. The rule
    engine reads this as a pre-computed scalar; it is never recomputed locally
    (rules must not perform series math). None when the payload omits it."""

    supertrend_direction: str | None = None
    """Supertrend(10, 2) direction: ``"up"`` (price above the band, long bias)
    or ``"down"`` (price below the band, short bias). Supplied by the Pine
    payload; None when unavailable."""

    opening_15m_open: Decimal | None = None
    opening_15m_high: Decimal | None = None
    opening_15m_low: Decimal | None = None
    opening_15m_close: Decimal | None = None
    """OHLC of the opening 15-minute candle of the session. Derived from
    persisted market-data candles at packet assembly; None when unavailable."""

    opening_15m_volume: int | None = None
    """Volume of the opening 15-minute candle (used by the short-sell setup's
    high-volume-selling condition)."""

    opening_15m_avg_volume: int | None = None
    """Average volume of the opening 15-minute candle across the trailing
    sessions (baseline for the short-sell setup's volume ratio)."""

    prev_day_high: Decimal | None = None
    prev_day_low: Decimal | None = None
    """Previous trading day's high/low, derived from persisted market-data
    candles at packet assembly; None when unavailable."""


@dataclass(frozen=True)
class OptionsContext:
    """Options chain snapshot (populated when options data is available)."""

    pcr: Decimal
    max_pain: Decimal
    atm_iv: Decimal
    oi_change_pct: Decimal
    unusual_activity: bool = False


@dataclass(frozen=True)
class BreadthContext:
    """Sector and index-level market breadth for context."""

    sector_index_change_pct: Decimal
    sector_advance_decline: Decimal
    nifty_change_pct: Decimal
    sensex_change_pct: Decimal


@dataclass(frozen=True)
class NewsItem:
    """Single news headline with NLP-derived attributes."""

    title: str
    source: str
    sentiment: AggregateSentiment
    materiality: MaterialityLevel
    age_minutes: int
    url: str = ""


@dataclass(frozen=True)
class NewsContext:
    """Aggregated news context for a symbol over a rolling window."""

    headlines: tuple[NewsItem, ...] = ()
    aggregate_sentiment: AggregateSentiment = AggregateSentiment.NEUTRAL


@dataclass(frozen=True)
class AnnouncementItem:
    """Single processed corporate announcement."""

    announcement_type: str
    title: str
    materiality: MaterialityLevel
    age_hours: float


@dataclass(frozen=True)
class PendingEvent:
    """A scheduled corporate event (e.g. earnings, AGM)."""

    event_type: str
    scheduled_at: datetime

    def __post_init__(self) -> None:
        if self.scheduled_at.tzinfo is None:
            raise ValueError(
                "PendingEvent.scheduled_at must be timezone-aware"
            )


@dataclass(frozen=True)
class AnnouncementContext:
    """Recent corporate announcements and pending scheduled events."""

    recent_announcements: tuple[AnnouncementItem, ...] = ()
    pending_events: tuple[PendingEvent, ...] = ()


@dataclass(frozen=True)
class GlobalContext:
    """Global market indicators that affect Indian equities."""

    dow_futures_pct: Decimal
    sgx_nifty_pct: Decimal
    crude_oil_pct: Decimal
    usd_inr_change_pct: Decimal
    vix: Decimal
    india_vix: Decimal
    fii_net_flow_cr: Decimal


@dataclass(frozen=True)
class Deal:
    """A single bulk or block deal record."""

    entity: str
    quantity: int
    price: Decimal
    side: str  # "BUY" | "SELL"


@dataclass(frozen=True)
class InstitutionalContext:
    """Bulk and block deal activity for a symbol."""

    bulk_deals: tuple[Deal, ...] = ()
    block_deals: tuple[Deal, ...] = ()


@dataclass(frozen=True)
class PatternMatch:
    """A historical day with similarity to the current IntelligencePacket."""

    date_str: str          # ISO-8601 date string (e.g. "2024-03-17")
    similarity_score: Decimal
    outcome_summary: str   # Brief description of what happened on that day


@dataclass(frozen=True)
class PatternContext:
    """Historical pattern matches provided by the Pattern Engine (Phase 6+)."""

    similar_dates: tuple[PatternMatch, ...] = ()
    top_analogue_summary: str = ""


@dataclass(frozen=True)
class DataQuality:
    """
    Quality assessment of the IntelligencePacket.

    The rule engine rejects packets below the configured minimum quality
    score (settings.INTELLIGENCE_MIN_QUALITY_SCORE).
    """

    quality_score: float = 1.0
    """0.0 (no data) to 1.0 (all sources fresh and available)."""

    missing_sources: tuple[str, ...] = ()
    """Source names that were unavailable during packet assembly."""

    stale_sources: tuple[str, ...] = ()
    """Source names that exceeded their freshness threshold."""


# ---------------------------------------------------------------------------
# IntelligencePacket — the central context object
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class IntelligencePacket:
    """
    A complete, point-in-time intelligence snapshot for a single symbol.

    Assembled by the Market Intelligence Engine and consumed by the Rule
    Engine and AI Orchestrator. Immutable after construction.

    Required fields must always be present; optional context blocks
    (options, announcements, etc.) are None when data is unavailable.
    """

    symbol: str
    timestamp: datetime
    freshness_validated: bool
    price_context: PriceContext
    technical_context: TechnicalContext
    breadth_context: BreadthContext
    news_context: NewsContext
    data_quality: DataQuality

    # Optional enrichment blocks — populated progressively by each processing layer
    options_context: OptionsContext | None = None
    announcement_context: AnnouncementContext | None = None
    global_context: GlobalContext | None = None
    institutional_context: InstitutionalContext | None = None
    pattern_context: PatternContext | None = None

    # Deterministic market regime (e.g. "BULLISH", "RANGING") detected during
    # packet assembly. Optional: absent for packets assembled without the
    # classifier inputs. Consumed by the rule engine to tag RuleExecution rows.
    regime: str | None = None

    def __post_init__(self) -> None:
        if self.timestamp.tzinfo is None:
            raise ValueError(
                "IntelligencePacket.timestamp must be timezone-aware. "
                f"Got naive datetime: {self.timestamp!r}"
            )


# ---------------------------------------------------------------------------
# Intelligence pipeline event payloads
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class PositionSnapshot:
    """Point-in-time position snapshot for a symbol (published by Portfolio service)."""

    symbol: str
    timestamp: datetime
    has_position: bool
    quantity: int = 0
    entry_price: Decimal | None = None
    current_price: Decimal | None = None
    unrealized_pnl_pct: Decimal | None = None
    days_in_position: int = 0
    stop_loss: Decimal | None = None
    target_price: Decimal | None = None

    def __post_init__(self) -> None:
        if self.timestamp.tzinfo is None:
            raise ValueError("PositionSnapshot.timestamp must be timezone-aware")


@dataclass(frozen=True)
class RiskStateSnapshot:
    """Point-in-time risk metrics snapshot (published by Risk service)."""

    timestamp: datetime
    portfolio_drawdown_pct: Decimal | None = None
    portfolio_beta: Decimal | None = None
    concentration_risk: str = "LOW"
    var_95_pct: Decimal | None = None
    india_vix: Decimal | None = None

    def __post_init__(self) -> None:
        if self.timestamp.tzinfo is None:
            raise ValueError("RiskStateSnapshot.timestamp must be timezone-aware")


# ---------------------------------------------------------------------------
# Enriched intelligence packet
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class EnrichedIntelligencePacket:
    """IntelligencePacket with portfolio and risk context attached.

    Produced by PortfolioRiskContextBuilder and consumed by the AI orchestrator /
    PromptManager via the ``intelligence:enriched`` EventBus stream.
    """

    packet: IntelligencePacket
    portfolio_context: PositionSnapshot | None = None
    risk_context: RiskStateSnapshot | None = None


# ---------------------------------------------------------------------------
# AnalysisEvent — the trigger object that flows from Rule Engine to AI
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class AnalysisEvent:
    """
    A structured event emitted by the Rule Engine when a rule fires.

    The AI Orchestrator receives this event and uses its intelligence_packet
    to assemble the full prompt context. The event is also stored in the
    audit log for compliance.

    Attributes:
        id:                   Unique event identifier (UUID4).
        event_type:           The rule category that triggered this event.
        symbol:               NSE/BSE stock symbol.
        timestamp:            When the event was detected (UTC, timezone-aware).
        rule_id:              Identifier of the specific rule that fired.
        trigger_data:         Rule-specific data explaining why the rule fired
                              (e.g. ``{"change_pct": "3.2", "threshold": "2.0"}``).
        intelligence_packet:  Full context snapshot at the time of detection.
    """

    id: uuid.UUID
    event_type: EventType
    symbol: str
    timestamp: datetime
    rule_id: str
    trigger_data: dict[str, Any] = field(default_factory=dict)
    intelligence_packet: IntelligencePacket | None = None

    def __post_init__(self) -> None:
        if self.timestamp.tzinfo is None:
            raise ValueError(
                "AnalysisEvent.timestamp must be timezone-aware. "
                f"Got naive datetime: {self.timestamp!r}"
            )
