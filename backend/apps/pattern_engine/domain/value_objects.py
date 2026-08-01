from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from enum import Enum

from core.events.event_types import MarketTrend


@dataclass(frozen=True)
class FeatureWeights:
    """Weighted similarity groups per ADR-007 §5.2.

    The weights must sum to exactly ``1.0`` (validated in ``__post_init__``).
    """

    price_action: Decimal = Decimal("0.30")
    technical_state: Decimal = Decimal("0.25")
    options: Decimal = Decimal("0.15")
    macro_global: Decimal = Decimal("0.20")
    breadth: Decimal = Decimal("0.10")

    def __post_init__(self) -> None:
        total = (
            self.price_action
            + self.technical_state
            + self.options
            + self.macro_global
            + self.breadth
        )
        for name, value in {
            "price_action": self.price_action,
            "technical_state": self.technical_state,
            "options": self.options,
            "macro_global": self.macro_global,
            "breadth": self.breadth,
        }.items():
            if value < 0:
                raise ValueError(f"FeatureWeights.{name} must be >= 0")
        if total != Decimal(1):
            raise ValueError(
                f"FeatureWeights must sum to 1.0, got {total}. "
                "Use the ADR-007 §5.2 weights (0.30/0.25/0.15/0.20/0.10)."
            )

    @classmethod
    def default(cls) -> FeatureWeights:
        return cls()


@dataclass(frozen=True)
class FeatureVector:
    """Normalised representation of a single trading session.

    Derived deterministically from the IntelligencePacket (or, for historical
    sessions, from OHLCV + Technical Analysis snapshots). Optional features
    (``None``) are excluded from similarity scoring and their group weight is
    reallocated predictably across the remaining groups.
    """

    symbol: str
    as_of: datetime
    price_change_pct: Decimal
    gap_pct: Decimal
    volume_ratio: Decimal
    rsi_14: Decimal | None
    macd_histogram: Decimal | None
    bb_position: Decimal | None
    trend: MarketTrend
    pcr: Decimal | None
    oi_change_direction: int | None
    nifty_change_pct: Decimal
    crude_oil_pct: Decimal | None
    fii_flow_direction: int | None
    sector_trend_direction: int | None
    advance_decline_ratio: Decimal | None


@dataclass(frozen=True)
class SimilarityScore:
    """Result of comparing one historical feature vector against the current one.

    Attributes:
        overall:           Weighted similarity in ``[0.0, 1.0]`` (1.0 = identical).
        feature_distance:  Raw, scale-heterogeneous Euclidean distance computed
                           *before* per-feature normalisation. Informational.
        per_group_distance: Distance ``[0.0, 1.0]`` per feature group, keyed by
                           group name.
    """

    overall: Decimal
    feature_distance: Decimal
    per_group_distance: dict[str, Decimal]


@dataclass(frozen=True)
class EvidenceItem:
    """A single deterministic, human-readable justification line."""

    description: str
    supporting_metric: str
    value: str


class _TrendNumeric(Enum):
    """Internal numeric projection of MarketTrend used only for distance math."""

    DOWNTREND = Decimal(-1)
    SIDEWAYS = Decimal(0)
    UPTREND = Decimal(1)


__all__ = [
    "EvidenceItem",
    "FeatureVector",
    "FeatureWeights",
    "MarketTrend",
    "SimilarityScore",
    "_TrendNumeric",
]
