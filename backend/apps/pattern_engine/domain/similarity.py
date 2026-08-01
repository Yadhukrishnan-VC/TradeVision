"""
TradeVision AI — Pattern Engine similarity scoring (pure domain).

Pure functions with no Django imports — importable in isolation for testing
and tooling, mirroring the isolation rule of ``core/events/event_types.py``.

Similarity model (ADR-007 §5.2):
    Weighted vector distance across five feature groups:

    | Feature Group  | Features Used                                 | Weight |
    |----------------|-----------------------------------------------|--------|
    | Price action   | Change %, gap %, volume ratio                 | 30%    |
    | Technical state| RSI, MACD histogram, BB position, trend       | 25%    |
    | Options        | PCR, OI change direction                      | 15%    |
    | Macro/Global   | Nifty %, crude %, FII net flow direction      | 20%    |
    | Breadth        | Sector trend direction, A/D ratio             | 10%    |

    Per-feature distance is a normalised Euclidean distance::

        d(f) = min(1.0, |a_f - b_f| / scale_f)

    where ``scale_f`` is the documented characteristic scale of feature ``f``.
    Group distance is the arithmetic mean of its available features. Overall
    distance is the weighted sum of available group distances (weights are
    reallocated proportionally across the groups that actually have data — a
    missing optional feature, e.g. no options data, never crashes and degrades
    weight allocation predictably). Overall similarity is ``1 - distance``.

    ``feature_distance`` is the raw, scale-heterogeneous Euclidean distance
    computed *before* normalisation — informational, used for audit/tuning.

Determinism contract:
    Same inputs ⇒ identical outputs. No randomness, no I/O, no AI.
"""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from typing import Any

from apps.pattern_engine.domain.value_objects import (
    FeatureVector,
    FeatureWeights,
    SimilarityScore,
)
from core.events.event_types import (
    BreadthContext,
    GlobalContext,
    MarketTrend,
    OptionsContext,
    PriceContext,
    TechnicalContext,
)

SIX_DP = Decimal("0.000001")

DEFAULT_WEIGHTS: FeatureWeights = FeatureWeights.default()

# ---------------------------------------------------------------------------
# Feature metadata — group membership, within-group equal weighting, and the
# characteristic normalisation scale used to turn raw values into a 0..1
# distance. Values outside these ranges clamp at 1.0.
# ---------------------------------------------------------------------------

_FEATURE_GROUPS: dict[str, tuple[str, ...]] = {
    "price_action": ("price_change_pct", "gap_pct", "volume_ratio"),
    "technical_state": ("rsi_14", "macd_histogram", "bb_position", "trend"),
    "options": ("pcr", "oi_change_direction"),
    "macro_global": ("nifty_change_pct", "crude_oil_pct", "fii_flow_direction"),
    "breadth": ("sector_trend_direction", "advance_decline_ratio"),
}

_FEATURE_SCALES: dict[str, Decimal] = {
    "price_change_pct": Decimal("5.0"),  # % points
    "gap_pct": Decimal("3.0"),  # % points
    "volume_ratio": Decimal("3.0"),  # multiple of 20d average
    "rsi_14": Decimal("50.0"),  # RSI 0..100 around 50
    "macd_histogram": Decimal("5.0"),  # indicator units
    "bb_position": Decimal("1.0"),  # already 0..1
    "trend": Decimal("1.0"),  # categorical, distance is |diff|/2
    "pcr": Decimal("2.0"),  # put/call ratio
    "oi_change_direction": Decimal("1.0"),  # -1/0/1
    "nifty_change_pct": Decimal("2.0"),  # % points
    "crude_oil_pct": Decimal("3.0"),  # % points
    "fii_flow_direction": Decimal("1.0"),  # -1/0/1
    "sector_trend_direction": Decimal("1.0"),  # -1/0/1
    "advance_decline_ratio": Decimal("2.0"),  # ratio
}

_WEIGHT_ATTR_BY_GROUP: dict[str, str] = {
    "price_action": "price_action",
    "technical_state": "technical_state",
    "options": "options",
    "macro_global": "macro_global",
    "breadth": "breadth",
}


def _sign(value: Decimal | None) -> int | None:
    """Directional projection: 1 / -1 / 0, or ``None`` when the input is."""
    if value is None:
        return None
    if value > 0:
        return 1
    if value < 0:
        return -1
    return 0


def _trend_numeric(value: MarketTrend | str | None) -> Decimal | None:
    """Project a MarketTrend onto {-1, 0, 1} for distance math."""
    if value is None:
        return None
    text = value.value if isinstance(value, MarketTrend) else str(value)
    mapping = {
        "UPTREND": Decimal(1),
        "SIDEWAYS": Decimal(0),
        "DOWNTREND": Decimal(-1),
    }
    return mapping.get(text.upper(), Decimal(0))


def _feature_value(name: str, value: Any) -> Decimal | None:
    if value is None:
        return None
    if name == "trend":
        return _trend_numeric(value)
    return value


def _bb_position(
    current_price: Decimal, bb_upper: Decimal | None, bb_lower: Decimal | None
) -> Decimal | None:
    """Normalised position of price within the Bollinger band (0..1)."""
    if (
        bb_upper is None
        or bb_lower is None
        or bb_upper <= bb_lower
        or current_price <= 0
    ):
        return None
    return ((current_price - bb_lower) / (bb_upper - bb_lower)).quantize(SIX_DP)


# ---------------------------------------------------------------------------
# Feature vector construction
# ---------------------------------------------------------------------------


def build_feature_vector(
    *,
    symbol: str,
    as_of: datetime,
    price_context: PriceContext,
    technical_context: TechnicalContext,
    breadth_context: BreadthContext,
    options_context: OptionsContext | None = None,
    global_context: GlobalContext | None = None,
) -> FeatureVector:
    """Assemble a ``FeatureVector`` from the IntelligencePacket context blocks.

    Price features are derived from ``price_context``; technical features come
    from ``technical_context`` (never recomputed here — Technical Analysis owns
    indicator production); options/macro/breadth features come from their
    respective optional context blocks and are ``None`` when absent.

    Args:
        symbol:            NSE/BSE symbol.
        as_of:             Session datetime (UTC, timezone-aware).
        price_context:     Frozen ``PriceContext`` from the IntelligencePacket.
        technical_context: Frozen ``TechnicalContext`` from the IntelligencePacket.
        breadth_context:   Frozen ``BreadthContext`` from the IntelligencePacket.
        options_context:   Optional ``OptionsContext``.
        global_context:    Optional ``GlobalContext``.

    Returns:
        A fully populated ``FeatureVector`` (optional features may be ``None``).
    """
    if as_of.tzinfo is None:
        raise ValueError("FeatureVector.as_of must be timezone-aware")

    prev_close = price_context.prev_close
    gap_pct = Decimal(0)
    if prev_close is not None and prev_close != 0:
        gap_pct = (
            (price_context.open_price - prev_close) / prev_close * Decimal(100)
        ).quantize(SIX_DP)

    volume_ratio = Decimal(0)
    if price_context.avg_volume_20d > 0:
        volume_ratio = (
            Decimal(price_context.volume) / Decimal(price_context.avg_volume_20d)
        ).quantize(SIX_DP)

    oi_change_direction: int | None = None
    pcr: Decimal | None = None
    if options_context is not None:
        pcr = options_context.pcr
        oi_change_direction = _sign(options_context.oi_change_pct)

    crude_oil_pct: Decimal | None = None
    fii_flow_direction: int | None = None
    if global_context is not None:
        crude_oil_pct = global_context.crude_oil_pct
        fii_flow_direction = _sign(global_context.fii_net_flow_cr)

    return FeatureVector(
        symbol=symbol.upper(),
        as_of=as_of,
        price_change_pct=(
            price_context.change_pct
            if price_context.change_pct is not None
            else Decimal(0)
        ).quantize(SIX_DP),
        gap_pct=gap_pct,
        volume_ratio=volume_ratio,
        rsi_14=technical_context.rsi_14,
        macd_histogram=technical_context.macd_histogram,
        bb_position=_bb_position(
            price_context.current_price,
            technical_context.bb_upper,
            technical_context.bb_lower,
        ),
        trend=technical_context.trend,
        pcr=pcr,
        oi_change_direction=oi_change_direction,
        nifty_change_pct=breadth_context.nifty_change_pct,
        crude_oil_pct=crude_oil_pct,
        fii_flow_direction=fii_flow_direction,
        sector_trend_direction=_sign(breadth_context.sector_index_change_pct),
        advance_decline_ratio=breadth_context.sector_advance_decline,
    )


# ---------------------------------------------------------------------------
# Similarity scoring
# ---------------------------------------------------------------------------


def _per_feature_distance(name: str, a: Decimal, b: Decimal) -> Decimal:
    va = _feature_value(name, a)
    vb = _feature_value(name, b)
    scale = _FEATURE_SCALES[name]
    raw = (abs(va - vb) / scale).quantize(SIX_DP)
    return min(Decimal(1), raw)


def compute_similarity(
    candidate: FeatureVector,
    reference: FeatureVector,
    weights: FeatureWeights = DEFAULT_WEIGHTS,
) -> SimilarityScore:
    """Score how closely ``candidate`` resembles ``reference``.

    Args:
        candidate: A historical session's feature vector.
        reference: The current session's feature vector.
        weights:   ``FeatureWeights`` (defaults to the ADR-007 §5.2 weights).

    Returns:
        A ``SimilarityScore`` with overall similarity (0..1), the raw
        pre-normalisation Euclidean ``feature_distance``, and per-group
        distances. Missing optional features are excluded and their group
        weight is reallocated proportionally across available groups.
    """
    overall_distance_sum = Decimal(0)
    available_weight_sum = Decimal(0)
    per_group_distance: dict[str, Decimal] = {}

    raw_sq_sum = Decimal(0)
    raw_weight_sum = Decimal(0)

    for group, features in _FEATURE_GROUPS.items():
        group_weight: Decimal = getattr(weights, _WEIGHT_ATTR_BY_GROUP[group])
        within_group_count = Decimal(len(features))

        distances: list[Decimal] = []
        for name in features:
            a = getattr(candidate, name)
            b = getattr(reference, name)
            if a is None or b is None:
                continue
            d = _per_feature_distance(name, a, b)
            distances.append(d)

            va = _feature_value(name, a)
            vb = _feature_value(name, b)
            feature_weight = (group_weight / within_group_count).quantize(SIX_DP)
            diff = va - vb
            raw_sq_sum += feature_weight * diff * diff
            raw_weight_sum += feature_weight

        if not distances:
            continue

        group_distance = (
            sum(distances, Decimal(0)) / Decimal(len(distances))
        ).quantize(SIX_DP)
        per_group_distance[group] = group_distance
        overall_distance_sum += group_weight * group_distance
        available_weight_sum += group_weight

    if available_weight_sum == 0:
        return SimilarityScore(
            overall=Decimal(0),
            feature_distance=Decimal(0),
            per_group_distance={},
        )

    overall_distance = (overall_distance_sum / available_weight_sum).quantize(SIX_DP)
    overall = max(Decimal(0), (Decimal(1) - overall_distance)).quantize(SIX_DP)

    feature_distance = Decimal(0)
    if raw_weight_sum > 0:
        feature_distance = (raw_sq_sum / raw_weight_sum).sqrt().quantize(SIX_DP)

    return SimilarityScore(
        overall=overall,
        feature_distance=feature_distance,
        per_group_distance=per_group_distance,
    )


def now_utc() -> datetime:
    """Timezone-aware UTC now (kept here so tests can patch it deterministically)."""
    return datetime.now(timezone.utc)


__all__ = [
    "DEFAULT_WEIGHTS",
    "build_feature_vector",
    "compute_similarity",
]
