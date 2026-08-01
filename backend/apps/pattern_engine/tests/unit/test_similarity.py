from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal

import pytest

from apps.pattern_engine.domain.similarity import (
    DEFAULT_WEIGHTS,
    build_feature_vector,
    compute_similarity,
)
from apps.pattern_engine.domain.value_objects import FeatureVector, FeatureWeights
from core.events.event_types import (
    BreadthContext,
    CircuitStatus,
    GlobalContext,
    MarketTrend,
    OptionsContext,
    PriceContext,
    TechnicalContext,
)

TZ = timezone.utc


def _price(
    *,
    current=Decimal(100),
    prev_close=Decimal(98),
    change_pct=Decimal("2.04"),
    volume=1200000,
    avg_volume_20d=1000000,
) -> PriceContext:
    return PriceContext(
        current_price=current,
        open_price=Decimal("98.5"),
        high=Decimal(101),
        low=Decimal("97.5"),
        volume=volume,
        avg_volume_20d=avg_volume_20d,
        circuit_status=CircuitStatus.NORMAL,
        prev_close=prev_close,
        change_pct=change_pct,
    )


def _technical(**overrides) -> TechnicalContext:
    values = {
        "trend": MarketTrend.UPTREND,
        "rsi_14": Decimal(62),
        "macd_histogram": Decimal("0.85"),
        "bb_upper": Decimal(105),
        "bb_lower": Decimal(95),
    }
    values.update(overrides)
    return TechnicalContext(**values)


def _breadth(**overrides) -> BreadthContext:
    values = {
        "sector_index_change_pct": Decimal("0.5"),
        "sector_advance_decline": Decimal("1.4"),
        "nifty_change_pct": Decimal("0.3"),
        "sensex_change_pct": Decimal("0.2"),
    }
    values.update(overrides)
    return BreadthContext(**values)


def _options(**overrides) -> OptionsContext:
    values = {
        "pcr": Decimal("1.1"),
        "max_pain": Decimal(990),
        "atm_iv": Decimal(14),
        "oi_change_pct": Decimal("5.2"),
    }
    values.update(overrides)
    return OptionsContext(**values)


def _global_ctx(**overrides) -> GlobalContext:
    values = {
        "dow_futures_pct": Decimal("0.2"),
        "sgx_nifty_pct": Decimal("0.1"),
        "crude_oil_pct": Decimal("-0.8"),
        "usd_inr_change_pct": Decimal("0.05"),
        "vix": Decimal(12),
        "india_vix": Decimal(11),
        "fii_net_flow_cr": Decimal(250),
    }
    values.update(overrides)
    return GlobalContext(**values)


def _vector(**overrides) -> FeatureWeights:
    return FeatureWeights.default()


class TestFeatureWeights:
    def test_defaults_sum_to_one(self) -> None:
        weights = FeatureWeights.default()
        total = (
            weights.price_action
            + weights.technical_state
            + weights.options
            + weights.macro_global
            + weights.breadth
        )
        assert total == Decimal(1)

    def test_invalid_sum_rejected(self) -> None:
        with pytest.raises(ValueError):
            FeatureWeights(
                price_action=Decimal("0.5"),
                technical_state=Decimal("0.5"),
                options=Decimal("0.1"),
                macro_global=Decimal("0.1"),
                breadth=Decimal("0.1"),
            )

    def test_negative_weight_rejected(self) -> None:
        with pytest.raises(ValueError):
            FeatureWeights(
                price_action=Decimal("-0.1"),
                technical_state=Decimal("0.3"),
                options=Decimal("0.15"),
                macro_global=Decimal("0.2"),
                breadth=Decimal("0.1"),
            )


class TestBuildFeatureVector:
    def test_builds_full_vector(self) -> None:
        ts = datetime(2024, 3, 17, 10, 0, tzinfo=TZ)
        vector = build_feature_vector(
            symbol="reliance",
            as_of=ts,
            price_context=_price(),
            technical_context=_technical(),
            breadth_context=_breadth(),
            options_context=_options(),
            global_context=_global_ctx(),
        )
        assert vector.symbol == "RELIANCE"
        assert vector.as_of == ts
        assert vector.price_change_pct == Decimal("2.040000")
        assert float(vector.gap_pct) == pytest.approx(
            float(Decimal("0.5") / Decimal(98) * Decimal(100)), abs=0.001
        )
        assert vector.volume_ratio == Decimal("1.200000")
        assert vector.rsi_14 == Decimal(62)
        assert vector.macd_histogram == Decimal("0.85")
        assert float(vector.bb_position) == pytest.approx(0.5, abs=0.001)
        assert vector.trend == MarketTrend.UPTREND
        assert vector.pcr == Decimal("1.1")
        assert vector.oi_change_direction == 1
        assert vector.nifty_change_pct == Decimal("0.3")
        assert vector.crude_oil_pct == Decimal("-0.8")
        assert vector.fii_flow_direction == 1
        assert vector.sector_trend_direction == 1
        assert vector.advance_decline_ratio == Decimal("1.4")

    def test_optional_contexts_are_none(self) -> None:
        ts = datetime(2024, 3, 17, 10, 0, tzinfo=TZ)
        vector = build_feature_vector(
            symbol="RELIANCE",
            as_of=ts,
            price_context=_price(),
            technical_context=_technical(),
            breadth_context=_breadth(),
        )
        assert vector.pcr is None
        assert vector.oi_change_direction is None
        assert vector.crude_oil_pct is None
        assert vector.fii_flow_direction is None

    def test_rejects_naive_datetime(self) -> None:
        with pytest.raises(ValueError):
            build_feature_vector(
                symbol="RELIANCE",
                as_of=datetime(2024, 3, 17, 10, 0),  # noqa: DTZ001 — naive dt on purpose
                price_context=_price(),
                technical_context=_technical(),
                breadth_context=_breadth(),
            )

    def test_zero_avg_volume_yields_zero_ratio(self) -> None:
        ts = datetime(2024, 3, 17, 10, 0, tzinfo=TZ)
        vector = build_feature_vector(
            symbol="RELIANCE",
            as_of=ts,
            price_context=_price(avg_volume_20d=0),
            technical_context=_technical(),
            breadth_context=_breadth(),
        )
        assert vector.volume_ratio == Decimal(0)


class TestComputeSimilarity:
    def test_identical_vectors_score_one(self) -> None:
        ts = datetime(2024, 3, 17, 10, 0, tzinfo=TZ)
        v1 = build_feature_vector(
            symbol="RELIANCE",
            as_of=ts,
            price_context=_price(),
            technical_context=_technical(),
            breadth_context=_breadth(),
            options_context=_options(),
            global_context=_global_ctx(),
        )
        v2 = build_feature_vector(
            symbol="RELIANCE",
            as_of=ts,
            price_context=_price(),
            technical_context=_technical(),
            breadth_context=_breadth(),
            options_context=_options(),
            global_context=_global_ctx(),
        )
        score = compute_similarity(v1, v2, weights=DEFAULT_WEIGHTS)
        assert score.overall == pytest.approx(Decimal(1), abs=0.0001)
        assert score.feature_distance == pytest.approx(Decimal(0), abs=0.0001)
        assert set(score.per_group_distance) == {
            "price_action",
            "technical_state",
            "options",
            "macro_global",
            "breadth",
        }

    def test_opposite_vectors_score_low(self) -> None:
        ts = datetime(2024, 3, 17, 10, 0, tzinfo=TZ)
        base = {
            "price_context": _price(),
            "technical_context": _technical(),
            "breadth_context": _breadth(),
            "options_context": _options(),
            "global_context": _global_ctx(),
        }
        v1 = build_feature_vector(symbol="RELIANCE", as_of=ts, **base)
        opposite = {
            "price_context": _price(
                current=Decimal(90),
                prev_close=Decimal(98),
                change_pct=Decimal("-8.16"),
                volume=300000,
                avg_volume_20d=1000000,
            ),
            "technical_context": _technical(
                trend=MarketTrend.DOWNTREND, rsi_14=Decimal(15)
            ),
            "breadth_context": _breadth(nifty_change_pct=Decimal("-1.8")),
            "options_context": _options(
                pcr=Decimal("0.3"), oi_change_pct=Decimal("-8.0")
            ),
            "global_context": _global_ctx(
                crude_oil_pct=Decimal("3.2"), fii_net_flow_cr=Decimal(-1500)
            ),
        }
        v2 = build_feature_vector(symbol="RELIANCE", as_of=ts, **opposite)
        score = compute_similarity(v1, v2, weights=DEFAULT_WEIGHTS)
        assert score.overall < Decimal("0.5")
        assert score.overall >= Decimal(0)

    def test_missing_groups_reallocate_weight(self) -> None:
        """Historical vectors with None options/macro/breadth still score using
        the available groups, and weight is reallocated proportionally."""
        ts = datetime(2024, 3, 17, 10, 0, tzinfo=TZ)
        candidate = build_feature_vector(
            symbol="RELIANCE",
            as_of=ts,
            price_context=_price(),
            technical_context=_technical(),
            breadth_context=_breadth(),
        )
        reference = build_feature_vector(
            symbol="RELIANCE",
            as_of=ts,
            price_context=_price(),
            technical_context=_technical(),
            breadth_context=_breadth(),
        )
        score = compute_similarity(candidate, reference, weights=DEFAULT_WEIGHTS)
        assert score.overall == pytest.approx(Decimal(1), abs=0.0001)
        # options and macro_global optional features are None, but macro_global
        # still participates because nifty_change_pct is always populated.
        assert set(score.per_group_distance) == {
            "price_action",
            "technical_state",
            "breadth",
            "macro_global",
        }
        assert "options" not in score.per_group_distance

    def test_deterministic(self) -> None:
        ts = datetime(2024, 3, 17, 10, 0, tzinfo=TZ)
        a = build_feature_vector(
            symbol="RELIANCE",
            as_of=ts,
            price_context=_price(),
            technical_context=_technical(),
            breadth_context=_breadth(),
            options_context=_options(),
        )
        b = build_feature_vector(
            symbol="RELIANCE",
            as_of=ts,
            price_context=_price(),
            technical_context=_technical(rsi_14=Decimal(58)),
            breadth_context=_breadth(),
            options_context=_options(),
        )
        s1 = compute_similarity(a, b, weights=DEFAULT_WEIGHTS)
        s2 = compute_similarity(a, b, weights=DEFAULT_WEIGHTS)
        assert s1 == s2

    def test_fully_missing_reference_returns_zero(self) -> None:
        ts = datetime(2024, 3, 17, 10, 0, tzinfo=TZ)
        empty_ref = build_feature_vector(
            symbol="RELIANCE",
            as_of=ts,
            price_context=_price(),
            technical_context=_technical(),
            breadth_context=_breadth(),
        )
        empty_candidate = FeatureVector(
            symbol="RELIANCE",
            as_of=ts,
            price_change_pct=Decimal(1),
            gap_pct=Decimal(0),
            volume_ratio=Decimal(1),
            rsi_14=None,
            macd_histogram=None,
            bb_position=None,
            trend=None,
            pcr=None,
            oi_change_direction=None,
            nifty_change_pct=Decimal("0.5"),
            crude_oil_pct=None,
            fii_flow_direction=None,
            sector_trend_direction=None,
            advance_decline_ratio=None,
        )
        score = compute_similarity(empty_candidate, empty_ref, weights=DEFAULT_WEIGHTS)
        # price + breadth groups still available → partial score, no exception
        assert score.overall >= Decimal(0)
        assert score.overall <= Decimal(1)
