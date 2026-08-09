"""Batch M3.6 — unit tests for the pure stop-loss evaluation logic."""

from __future__ import annotations

from decimal import Decimal

import pytest

from apps.portfolio.application.exit_evaluation_service import evaluate_stop


class TestEvaluateStopLong:
    def test_triggers_when_low_below_stop(self) -> None:
        triggered, exit_price = evaluate_stop(
            "LONG", Decimal("95.00"), Decimal("103.00"), Decimal("94.50")
        )
        assert triggered is True
        assert exit_price == Decimal("94.50")

    def test_does_not_trigger_when_low_above_stop(self) -> None:
        triggered, _ = evaluate_stop(
            "LONG", Decimal("95.00"), Decimal("103.00"), Decimal("96.00")
        )
        assert triggered is False

    def test_equality_boundary_triggers(self) -> None:
        triggered, exit_price = evaluate_stop(
            "LONG", Decimal("95.00"), Decimal("103.00"), Decimal("95.00")
        )
        assert triggered is True
        assert exit_price == Decimal("95.00")


class TestEvaluateStopShort:
    def test_triggers_when_high_above_stop(self) -> None:
        triggered, exit_price = evaluate_stop(
            "SHORT", Decimal("110.00"), Decimal("111.50"), Decimal("100.00")
        )
        assert triggered is True
        assert exit_price == Decimal("111.50")

    def test_does_not_trigger_when_high_below_stop(self) -> None:
        triggered, _ = evaluate_stop(
            "SHORT", Decimal("110.00"), Decimal("109.00"), Decimal("100.00")
        )
        assert triggered is False

    def test_equality_boundary_triggers(self) -> None:
        triggered, exit_price = evaluate_stop(
            "SHORT", Decimal("110.00"), Decimal("110.00"), Decimal("100.00")
        )
        assert triggered is True
        assert exit_price == Decimal("110.00")


class TestGapThroughPricingDecisionA:
    """Decision A: gap-through fills at the worse of stop or extreme."""

    def test_long_gap_fills_at_worse_of_stop_or_low(self) -> None:
        # Stop at 95, bar low gaps down to 90 -> fill at 90 (worse), not 95.
        triggered, exit_price = evaluate_stop(
            "LONG", Decimal("95.00"), Decimal("96.00"), Decimal("90.00")
        )
        assert triggered is True
        assert exit_price == Decimal("90.00")

    def test_short_gap_fills_at_worse_of_stop_or_high(self) -> None:
        # Stop at 110, bar high gaps up to 115 -> fill at 115 (worse), not 110.
        triggered, exit_price = evaluate_stop(
            "SHORT", Decimal("110.00"), Decimal("115.00"), Decimal("108.00")
        )
        assert triggered is True
        assert exit_price == Decimal("115.00")

    def test_non_gap_trigger_fills_at_stop(self) -> None:
        # Low just touches stop (95) without moving through it -> fill at 95.
        triggered, exit_price = evaluate_stop(
            "LONG", Decimal("95.00"), Decimal("96.00"), Decimal("95.00")
        )
        assert triggered is True
        assert exit_price == Decimal("95.00")


class TestEvaluateStopUnknownSide:
    def test_unknown_side_never_triggers(self) -> None:
        triggered, exit_price = evaluate_stop(
            "NEUTRAL", Decimal("95.00"), Decimal("103.00"), Decimal("90.00")
        )
        assert triggered is False
        assert exit_price == Decimal("95.00")
