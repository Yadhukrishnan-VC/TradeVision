"""
Batch AI-5B — Pattern/Market Context reaches the rendered prompt, and the
template↔validator contract is single-source-of-truth.

Smoke tests for fixes #1/#2/#3 (AI-5B):
    - PromptManager.render() forwards the six context scores, overall
      context confidence, and pattern_alignment_note into the template.
    - The rendered prompt contains those values (string-level, not just the
      signal_context dict).
    - The template instructs the LLM to emit ``direction`` (the canonical
      field) and the live validator accepts that payload.
    - Rendering with defaulted values never leaks Jinja delimiters.
"""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from decimal import Decimal

import pytest

pytestmark = pytest.mark.django_db


def _populated_signal_context() -> dict:
    return {
        "pine_output": "{}",
        "market_regime": "BULLISH",
        "multi_timeframe_alignment": "BULLISH_ALIGNED",
        "news_headlines": [],
        "sector_context": "Auto sector",
        "event": {
            "change_pct": 3.5,
            "current_price": 100,
            "volume_ratio": 1.5,
            "circuit_status": "NONE",
        },
        "bullishness_score": 0.74,
        "bearishness_score": 0.11,
        "volatility_score": 0.32,
        "trend_score": 0.68,
        "liquidity_score": 0.81,
        "momentum_score": 0.63,
        "overall_context_confidence": 0.88,
        "pattern_alignment_note": "Similar to 2024-03-17: price rose 2%",
    }


def _defaulted_signal_context() -> dict:
    return {
        "pine_output": "{}",
        "market_regime": "UNKNOWN",
        "multi_timeframe_alignment": "NEUTRAL",
        "news_headlines": [],
        "sector_context": "",
        "event": {
            "change_pct": 0,
            "current_price": 0,
            "volume_ratio": 0,
            "circuit_status": "NONE",
        },
        "bullishness_score": 0.0,
        "bearishness_score": 0.0,
        "volatility_score": 0.0,
        "trend_score": 0.0,
        "liquidity_score": 0.0,
        "momentum_score": 0.0,
        "overall_context_confidence": 0.0,
        "pattern_alignment_note": "PATTERN_ENGINE_NOT_AVAILABLE",
    }


class TestPromptManagerForwardsPatternContext:
    def test_rendered_prompt_contains_all_six_scores(self) -> None:
        from apps.ai_engine.prompt_manager.service import PromptManager

        prompt = PromptManager().render(
            event_type="price_movement",
            signal_context=_populated_signal_context(),
        )

        assert "0.74" in prompt  # bullishness_score
        assert "0.11" in prompt  # bearishness_score
        assert "0.32" in prompt  # volatility_score
        assert "0.68" in prompt  # trend_score
        assert "0.81" in prompt  # liquidity_score
        assert "0.63" in prompt  # momentum_score
        assert "0.88" in prompt  # overall_context_confidence
        assert "Similar to 2024-03-17: price rose 2%" in prompt

    def test_rendered_prompt_contains_labels(self) -> None:
        from apps.ai_engine.prompt_manager.service import PromptManager

        prompt = PromptManager().render(
            event_type="volume_spike",
            signal_context=_populated_signal_context(),
        )

        assert "Bullishness:" in prompt
        assert "Bearishness:" in prompt
        assert "Volatility:" in prompt
        assert "Trend:" in prompt
        assert "Liquidity:" in prompt
        assert "Momentum:" in prompt
        assert "Overall Context Confidence:" in prompt
        assert "PATTERN ALIGNMENT:" in prompt

    def test_rendered_prompt_defaults_never_leak_jinja(self) -> None:
        from apps.ai_engine.prompt_manager.service import PromptManager

        prompt = PromptManager().render(
            event_type="breakdown",
            signal_context=_defaulted_signal_context(),
        )

        assert "{{" not in prompt
        assert "}}" not in prompt
        assert "PATTERN_ENGINE_NOT_AVAILABLE" in prompt

    def test_template_instructs_direction_not_signal(self) -> None:
        from apps.ai_engine.prompt_manager.service import PromptManager

        prompt = PromptManager().render(
            event_type="price_movement",
            signal_context=_populated_signal_context(),
        )

        assert '"direction"' in prompt
        assert '"signal"' not in prompt


class TestTemplateValidatorContract:
    def test_direction_payload_passes_live_validator(self) -> None:
        from core.ai.base_provider import AIRawResponse
        from core.ai.validator import AIResponseValidator

        raw = AIRawResponse(
            request_id=uuid.uuid4(),
            provider="deepseek",
            raw_text=json.dumps(
                {
                    "direction": "BUY",
                    "confidence_score": 0.85,
                    "reasoning": "x" * 30,
                    "risk_level": "LOW",
                    "risk_explanation": "z" * 15,
                    "key_factors": ["RSI bullish"],
                    "contradicting_factors": [],
                    "time_horizon": "SHORT",
                    "follow_up_triggers": [],
                }
            ),
            input_tokens=100,
            output_tokens=50,
            latency_ms=500.0,
            estimated_cost_usd=Decimal("0.001"),
            timestamp=datetime.now(timezone.utc),
        )

        validated = AIResponseValidator().validate(raw)
        assert validated.direction == "BUY"
        assert validated.confidence_score == 0.85

    def test_signal_key_payload_is_rejected(self) -> None:
        from core.ai.base_provider import AIRawResponse
        from core.ai.exceptions import AIResponseValidationError
        from core.ai.validator import AIResponseValidator

        raw = AIRawResponse(
            request_id=uuid.uuid4(),
            provider="deepseek",
            raw_text=json.dumps(
                {
                    "signal": "BUY",
                    "confidence_score": 0.85,
                    "reasoning": "x" * 30,
                    "risk_level": "LOW",
                    "risk_explanation": "z" * 15,
                    "key_factors": ["RSI bullish"],
                    "contradicting_factors": [],
                    "time_horizon": "SHORT",
                    "follow_up_triggers": [],
                }
            ),
            input_tokens=100,
            output_tokens=50,
            latency_ms=500.0,
            estimated_cost_usd=Decimal("0.001"),
            timestamp=datetime.now(timezone.utc),
        )

        with pytest.raises(AIResponseValidationError):
            AIResponseValidator().validate(raw)
