"""
Batch AI-5D — Numeric Pattern Confidence Feed integration tests.

Seeds a real ``PatternAnalysisRun`` and drives the orchestrator's
``orchestrate`` chain to prove the numeric feed is gated on
``CONFIDENCE_ENGINE_V2_ENABLED`` and lands in the persisted
``ConfidenceEvaluation.adjustment_reasons``.
"""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from decimal import Decimal
from unittest.mock import MagicMock, patch

import pytest
from django.test import override_settings

pytestmark = pytest.mark.django_db


def _seed_pattern_run(
    symbol: str = "RELIANCE",
    *,
    contribution: str = "0.2000",
    accuracy: str | None = "0.4000",
) -> None:
    from apps.pattern_engine.infrastructure.models import PatternAnalysisRun

    PatternAnalysisRun.objects.create(
        symbol=symbol,
        as_of=datetime.now(timezone.utc),
        top_analogue_summary="Top analogue test",
        confidence_contribution=Decimal(contribution),
        historical_recommendation_accuracy=(
            Decimal(accuracy) if accuracy is not None else None
        ),
        matched_patterns=[],
        evidence=[],
    )


def _rule_fired_event() -> object:
    from apps.eventbus.domain.events import DomainEvent

    return DomainEvent.create(
        event_type="rule_engine.RuleFired",
        payload={
            "symbol": "RELIANCE",
            "rule_id": "price_movement_rule",
            "event_type": "price_movement",
            "severity": "HIGH",
            "trigger_data": {"change_pct": "3.5", "indicators": {"rsi_14": 62.5}},
            "analysis_event_id": str(uuid.uuid4()),
        },
        correlation_id=uuid.uuid4(),
    )


def _valid_raw_response() -> MagicMock:
    content = json.dumps({
        "direction": "BUY",
        "confidence_score": 0.60,
        "reasoning": "Strong technical setup with sufficient length for the schema",
        "risk_level": "LOW",
        "risk_explanation": "Risk explanation with sufficient length for the schema",
        "key_factors": ["RSI bullish"],
        "contradicting_factors": [],
        "time_horizon": "SHORT",
        "follow_up_triggers": [],
    })
    return MagicMock(
        provider="deepseek",
        raw_text=content,
        input_tokens=100,
        output_tokens=50,
        latency_ms=1200.0,
        estimated_cost_usd=Decimal("0.001"),
        timestamp=datetime.now(timezone.utc),
    )


def _patch_orchestrator_deps(provider_mock) -> list:
    """Patch orchestrator deps so ``orchestrate`` runs synchronously with a
    validated response, returning the list of active patchers."""

    from apps.ai_engine.infrastructure.ai_reasoning_orchestrator import (
        AIReasoningOrchestrator,
    )
    from apps.ai_engine.model_router import ModelRouter
    from apps.ai_engine.tests.test_ai5c_breaker_feedback import _mock_redis
    from core.resilience.circuit_breaker import CircuitBreakerFactory

    factory = CircuitBreakerFactory(_mock_redis())
    router = ModelRouter(factory)

    validated = MagicMock(
        direction="BUY",
        confidence_score=0.60,
        reasoning="Strong technical setup",
        risk_level="LOW",
        risk_explanation="Standard risk",
        key_factors=("RSI bullish",),
        contradicting_factors=(),
        time_horizon="SHORT",
        follow_up_triggers=(),
    )

    patchers = [
        patch.object(AIReasoningOrchestrator, "_match_strategy", return_value=None),
        patch.object(AIReasoningOrchestrator, "_render_prompt", return_value="test prompt"),
        patch.object(AIReasoningOrchestrator, "_call_ai", return_value=provider_mock),
        patch.object(AIReasoningOrchestrator, "_validate_response", return_value=validated),
        patch(
            "apps.ai_engine.infrastructure.ai_reasoning_orchestrator.CircuitBreakerFactory",
            return_value=factory,
        ),
        patch(
            "apps.ai_engine.infrastructure.ai_reasoning_orchestrator.ModelRouter",
            return_value=router,
        ),
    ]
    for patcher in patchers:
        patcher.start()
    return patchers


def _stop_patchers(patchers: list) -> None:
    for patcher in patchers:
        patcher.stop()


class TestPatternFeedGatedIntegration:
    def test_v2_enabled_feed_applies_and_persists_reasons(self) -> None:
        from apps.ai_engine.infrastructure.ai_reasoning_orchestrator import (
            AIReasoningOrchestrator,
        )
        from apps.ai_engine.models import ConfidenceEvaluation
        from apps.eventbus.infrastructure.event_bus_factory import (
            reset_event_bus,
        )

        _seed_pattern_run(contribution="0.2000", accuracy="0.4000")

        event = _rule_fired_event()
        patchers = _patch_orchestrator_deps(_valid_raw_response())
        try:
            with override_settings(CONFIDENCE_ENGINE_V2_ENABLED=True):
                reset_event_bus()
                orchestrator = AIReasoningOrchestrator()
                result = orchestrator.orchestrate(event)
        finally:
            _stop_patchers(patchers)

        assert result is not None
        assert result["confidence_score"] == 0.75

        evaluation = ConfidenceEvaluation.objects.filter(
            packet_id=str(event.event_id),
        ).first()
        assert evaluation is not None
        assert any("pattern confidence contribution: +0.2000" in r for r in evaluation.adjustment_reasons)
        assert any("pattern accuracy penalty: accuracy=0.4000, penalty=0.0500" in r for r in evaluation.adjustment_reasons)

    def test_v2_disabled_feed_is_noop_with_seeded_run(self) -> None:
        from apps.ai_engine.infrastructure.ai_reasoning_orchestrator import (
            AIReasoningOrchestrator,
        )
        from apps.ai_engine.models import ConfidenceEvaluation
        from apps.eventbus.infrastructure.event_bus_factory import (
            reset_event_bus,
        )

        _seed_pattern_run(contribution="0.2000", accuracy="0.4000")

        event = _rule_fired_event()
        patchers = _patch_orchestrator_deps(_valid_raw_response())
        try:
            reset_event_bus()
            orchestrator = AIReasoningOrchestrator()
            result = orchestrator.orchestrate(event)
        finally:
            _stop_patchers(patchers)

        assert result is not None
        assert result["confidence_score"] == 0.60

        evaluation = ConfidenceEvaluation.objects.filter(
            packet_id=str(event.event_id),
        ).first()
        assert evaluation is not None
        assert not any("pattern confidence" in r for r in evaluation.adjustment_reasons)
        assert not any("pattern accuracy" in r for r in evaluation.adjustment_reasons)

    def test_no_run_seeded_feed_noops(self) -> None:
        from apps.ai_engine.infrastructure.ai_reasoning_orchestrator import (
            AIReasoningOrchestrator,
        )
        from apps.ai_engine.models import ConfidenceEvaluation
        from apps.eventbus.infrastructure.event_bus_factory import (
            reset_event_bus,
        )

        event = _rule_fired_event()
        patchers = _patch_orchestrator_deps(_valid_raw_response())
        try:
            with override_settings(CONFIDENCE_ENGINE_V2_ENABLED=True):
                reset_event_bus()
                orchestrator = AIReasoningOrchestrator()
                result = orchestrator.orchestrate(event)
        finally:
            _stop_patchers(patchers)

        assert result is not None
        assert result["confidence_score"] == 0.60

        evaluation = ConfidenceEvaluation.objects.filter(
            packet_id=str(event.event_id),
        ).first()
        assert evaluation is not None
        assert not any("pattern confidence" in r for r in evaluation.adjustment_reasons)

    def test_lookup_failure_is_graceful(self) -> None:
        from apps.ai_engine.infrastructure.ai_reasoning_orchestrator import (
            AIReasoningOrchestrator,
        )

        event = _rule_fired_event()
        patchers = _patch_orchestrator_deps(_valid_raw_response())
        try:
            with (
                override_settings(CONFIDENCE_ENGINE_V2_ENABLED=True),
                patch(
                    "apps.pattern_engine.infrastructure.repositories.PatternAnalysisRunRepository"
                ) as mock_repo_cls,
            ):
                mock_repo = MagicMock()
                mock_repo.latest_for_symbol.side_effect = RuntimeError("redis down")
                mock_repo_cls.return_value = mock_repo

                orchestrator = AIReasoningOrchestrator()
                result = orchestrator.orchestrate(event)
        finally:
            _stop_patchers(patchers)

        assert result is not None
        assert result["confidence_score"] == 0.60
