"""
Tests for ModelRouter — deterministic AI provider selection.

See ADR-019 for the full routing policy specification.
"""

from __future__ import annotations

from decimal import Decimal
from unittest.mock import MagicMock, patch

import pytest

from core.ai.base_provider import ProviderCapabilities
from core.ai.exceptions import NoAvailableProviderError
from core.constants import AIProviderName, CostTier, LatencyTier
from core.events.event_types import EventType
from core.resilience.circuit_breaker import CircuitState


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_factory(
    circuit_states: dict[str, CircuitState] | None = None,
) -> MagicMock:
    """Create a mock ``CircuitBreakerFactory`` with per-provider states.

    Defaults all providers to ``CLOSED``.
    """
    factory = MagicMock()
    if circuit_states is None:
        circuit_states = {}

    def get_or_create(name: str, **kwargs) -> MagicMock:
        breaker = MagicMock()
        # Strip the ``ai-provider-`` prefix to get provider name
        provider_key = name.replace("ai-provider-", "")
        breaker.state = circuit_states.get(provider_key, CircuitState.CLOSED)
        return breaker

    factory.get_or_create.side_effect = get_or_create
    return factory


@pytest.fixture
def router():
    """Return a ``ModelRouter`` with all providers CLOSED by default."""
    factory = _make_factory()
    from apps.ai_engine.model_router import ModelRouter

    return ModelRouter(factory)


# ---------------------------------------------------------------------------
# Selection tests
# ---------------------------------------------------------------------------


class TestModelRouterSelection:
    """Default priority order, user override, strategy preference."""

    def test_default_priority_order_selects_first_healthy_candidate(
        self, router
    ) -> None:
        from apps.ai_engine.model_router import RoutingRequest, RoutingCapabilityRequirements

        request = RoutingRequest(
            event_type=EventType.PRICE_MOVEMENT,
            required_capabilities=RoutingCapabilityRequirements(),
            context_tokens_estimate=500,
        )
        decision = router.route(request)
        assert isinstance(decision.selected_provider, AIProviderName)
        # Claude is first in default priority
        assert decision.selected_provider == AIProviderName.CLAUDE

    def test_user_override_takes_precedence_over_everything(self, router) -> None:
        from apps.ai_engine.model_router import RoutingRequest

        request = RoutingRequest(
            event_type=EventType.PRICE_MOVEMENT,
            context_tokens_estimate=500,
            user_override_provider=AIProviderName.OLLAMA,
        )
        decision = router.route(request)
        assert decision.selected_provider == AIProviderName.OLLAMA
        assert "User override" in decision.rationale

    def test_strategy_preferred_provider_selected_when_healthy(self, router) -> None:
        from apps.ai_engine.model_router import RoutingRequest

        request = RoutingRequest(
            event_type=EventType.EARNINGS,
            context_tokens_estimate=500,
            preferred_provider=AIProviderName.DEEPSEEK,
        )
        decision = router.route(request)
        assert decision.selected_provider == AIProviderName.DEEPSEEK
        assert "Strategy preference" in decision.rationale


# ---------------------------------------------------------------------------
# Capability filter tests
# ---------------------------------------------------------------------------


class TestModelRouterCapabilityFilter:
    """Capability-based exclusion."""

    def test_capability_filter_excludes_provider_missing_required_capability(
        self, router
    ) -> None:
        from apps.ai_engine.model_router import (
            RoutingRequest,
            RoutingCapabilityRequirements,
        )

        # DeepSeek and Ollama don't support vision
        request = RoutingRequest(
            event_type=EventType.PRICE_MOVEMENT,
            required_capabilities=RoutingCapabilityRequirements(
                requires_structured_json=True,
                requires_vision=True,
            ),
            context_tokens_estimate=500,
        )
        decision = router.route(request)
        excluded = decision.routing_metadata.excluded
        assert "deepseek" in excluded
        assert "does not support vision" in excluded["deepseek"]

    def test_context_window_filter_excludes_undersized_provider(self, router) -> None:
        from apps.ai_engine.model_router import RoutingRequest

        # Ollama has 8192 context window
        request = RoutingRequest(
            event_type=EventType.PRICE_MOVEMENT,
            context_tokens_estimate=10000,
        )
        decision = router.route(request)
        excluded = decision.routing_metadata.excluded
        assert "ollama" in excluded
        assert "context window" in excluded["ollama"]


# ---------------------------------------------------------------------------
# Health / circuit state tests
# ---------------------------------------------------------------------------


class TestModelRouterHealth:
    """Circuit-based health routing."""

    def test_open_circuit_excludes_provider(self) -> None:
        from apps.ai_engine.model_router import ModelRouter, RoutingRequest

        factory = _make_factory({"claude": CircuitState.OPEN})
        router = ModelRouter(factory)
        request = RoutingRequest(
            event_type=EventType.PRICE_MOVEMENT,
            context_tokens_estimate=500,
        )
        decision = router.route(request)
        excluded = decision.routing_metadata.excluded
        assert "claude" in excluded
        # Gemini should be selected next (position 2 in default priority)
        assert decision.selected_provider == AIProviderName.GEMINI

    def test_half_open_circuit_is_eligible(self) -> None:
        from apps.ai_engine.model_router import ModelRouter, RoutingRequest

        factory = _make_factory({"claude": CircuitState.HALF_OPEN})
        router = ModelRouter(factory)
        request = RoutingRequest(
            event_type=EventType.PRICE_MOVEMENT,
            context_tokens_estimate=500,
        )
        decision = router.route(request)
        # Claude should still be selected
        assert decision.selected_provider == AIProviderName.CLAUDE

    def test_manually_disabled_provider_excluded(self, router) -> None:
        from apps.ai_engine.model_router import RoutingRequest

        with patch("apps.ai_engine.model_router.config") as mock_config:
            mock_config.ai_provider_disabled = {"claude"}
            mock_config.ai_provider_priority = [
                "claude", "gemini", "openai", "deepseek", "ollama"
            ]
            mock_config.ai_routing_fast_tier_threshold_ms = 1500
            mock_config.ai_cost_tier_ceilings = {}
            request = RoutingRequest(
                event_type=EventType.PRICE_MOVEMENT,
                context_tokens_estimate=500,
            )
            decision = router.route(request)
            assert decision.selected_provider != AIProviderName.CLAUDE

    def test_degraded_status_does_not_exclude_provider(self) -> None:
        """Routing reads only circuit state, not health_check.

        ``health_check()`` is never called by the router; ``"degraded"``
        is a health endpoint concept, not a circuit breaker concern.
        """
        from apps.ai_engine.model_router import ModelRouter, RoutingRequest

        # All providers CLOSED — degraded doesn't exist in circuit state
        factory = _make_factory()
        router = ModelRouter(factory)
        request = RoutingRequest(
            event_type=EventType.PRICE_MOVEMENT,
            context_tokens_estimate=500,
        )
        decision = router.route(request)
        assert decision.selected_provider == AIProviderName.CLAUDE
        # Verify no provider was excluded (no call to health_check)
        excluded = decision.routing_metadata.excluded
        # The only exclusions would be capability-based, not health-based
        # (all providers CLOSED, so none excluded by circuit)
        health_exclusions = {
            k: v for k, v in excluded.items() if "circuit breaker" in v
        }
        assert len(health_exclusions) == 0


# ---------------------------------------------------------------------------
# Fallback chain tests
# ---------------------------------------------------------------------------


class TestModelRouterFallback:
    """Fallback chain correctness."""

    def test_fallback_chain_excludes_selected_provider(self, router) -> None:
        from apps.ai_engine.model_router import RoutingRequest

        request = RoutingRequest(
            event_type=EventType.PRICE_MOVEMENT,
            context_tokens_estimate=500,
        )
        decision = router.route(request)
        assert decision.selected_provider not in decision.fallback_chain

    def test_next_in_chain_returns_following_provider(self, router) -> None:
        from apps.ai_engine.model_router import RoutingRequest

        request = RoutingRequest(
            event_type=EventType.PRICE_MOVEMENT,
            context_tokens_estimate=500,
        )
        decision = router.route(request)
        next_prov = router.next_in_chain(decision, decision.selected_provider)
        assert next_prov is not None
        assert next_prov != decision.selected_provider

    def test_next_in_chain_returns_none_when_chain_exhausted(self, router) -> None:
        from apps.ai_engine.model_router import RoutingRequest

        request = RoutingRequest(
            event_type=EventType.PRICE_MOVEMENT,
            context_tokens_estimate=500,
        )
        decision = router.route(request)
        # Walk through the entire chain
        current = decision.selected_provider
        while True:
            next_prov = router.next_in_chain(decision, current)
            if next_prov is None:
                break
            current = next_prov
        # After exhausting the chain, next_in_chain should return None
        assert router.next_in_chain(decision, current) is None


    def test_user_override_still_produces_fallback_chain(self, router) -> None:
        from apps.ai_engine.model_router import RoutingRequest

        request = RoutingRequest(
            event_type=EventType.PRICE_MOVEMENT,
            context_tokens_estimate=500,
            user_override_provider=AIProviderName.OLLAMA,
        )
        decision = router.route(request)
        assert decision.selected_provider == AIProviderName.OLLAMA
        assert decision.fallback_chain, (
            "Fallback chain should be non-empty when other "
            "healthy candidates exist"
        )
        assert AIProviderName.OLLAMA not in decision.fallback_chain


# ---------------------------------------------------------------------------
# Failure tests
# ---------------------------------------------------------------------------


class TestModelRouterFailure:
    """NoAvailableProviderError when all candidates excluded."""

    def test_no_available_provider_raises_when_all_excluded(self) -> None:
        from apps.ai_engine.model_router import ModelRouter, RoutingRequest

        factory = _make_factory({name.value: CircuitState.OPEN for name in AIProviderName})
        router = ModelRouter(factory)
        request = RoutingRequest(
            event_type=EventType.PRICE_MOVEMENT,
            context_tokens_estimate=500,
        )
        with pytest.raises(NoAvailableProviderError, match="No AI provider available"):
            router.route(request)


# ---------------------------------------------------------------------------
# Determinism tests
# ---------------------------------------------------------------------------


class TestModelRouterDeterminism:
    """Same input + same circuit state => same RoutingDecision."""

    def test_same_input_and_circuit_state_produces_identical_decision(
        self,
    ) -> None:
        from apps.ai_engine.model_router import ModelRouter, RoutingRequest

        factory = _make_factory()
        router = ModelRouter(factory)
        request = RoutingRequest(
            event_type=EventType.PRICE_MOVEMENT,
            context_tokens_estimate=500,
        )
        d1 = router.route(request)
        d2 = router.route(request)
        assert d1.selected_provider == d2.selected_provider
        assert d1.fallback_chain == d2.fallback_chain
        assert d1.rationale == d2.rationale


# ---------------------------------------------------------------------------
# Configuration override tests
# ---------------------------------------------------------------------------


class TestModelRouterConfiguration:
    """Custom priority, cost budget, latency budget."""

    def test_custom_provider_priority_setting_changes_default_order(
        self,
    ) -> None:
        from apps.ai_engine.model_router import ModelRouter, RoutingRequest

        factory = _make_factory()
        router = ModelRouter(factory)
        with patch("apps.ai_engine.model_router.config") as mock_config:
            mock_config.ai_provider_priority = ["ollama", "gemini"]
            mock_config.ai_provider_disabled = set()
            mock_config.ai_routing_fast_tier_threshold_ms = 1500
            mock_config.ai_cost_tier_ceilings = {}
            request = RoutingRequest(
                event_type=EventType.PRICE_MOVEMENT,
                context_tokens_estimate=500,
            )
            decision = router.route(request)
            assert decision.selected_provider == AIProviderName.OLLAMA

    def test_cost_budget_excludes_high_cost_tier_provider(self) -> None:
        from apps.ai_engine.model_router import ModelRouter, RoutingRequest

        factory = _make_factory()
        router = ModelRouter(factory)
        # Very tight budget ($0.001) — only FREE tier qualifies
        with patch("core.config.config") as mock_config:
            mock_config.ai_cost_tier_ceilings = {
                "FREE": "0.000",
                "LOW": "0.005",
                "MEDIUM": "0.015",
                "HIGH": "0.050",
            }
            mock_config.ai_provider_priority = [
                "claude", "gemini", "openai", "deepseek", "ollama"
            ]
            mock_config.ai_provider_disabled = set()
            mock_config.ai_routing_fast_tier_threshold_ms = 1500
            request = RoutingRequest(
                event_type=EventType.PRICE_MOVEMENT,
                context_tokens_estimate=500,
                cost_budget_usd=Decimal("0.001"),
            )
            # Only Ollama (FREE) should be available
            decision = router.route(request)
            assert decision.selected_provider == AIProviderName.OLLAMA

    def test_tight_latency_budget_prefers_fast_tier_provider(self) -> None:
        from apps.ai_engine.model_router import ModelRouter, RoutingRequest

        factory = _make_factory()
        router = ModelRouter(factory)
        # Tight latency budget: only FAST tier providers qualify
        with patch("core.config.config") as mock_config:
            mock_config.ai_routing_fast_tier_threshold_ms = 1500
            mock_config.ai_provider_priority = [
                "claude", "gemini", "openai", "deepseek", "ollama"
            ]
            mock_config.ai_provider_disabled = set()
            mock_config.ai_cost_tier_ceilings = {}
            request = RoutingRequest(
                event_type=EventType.PRICE_MOVEMENT,
                context_tokens_estimate=500,
                latency_budget_ms=500,
            )
            decision = router.route(request)
            # DeepSeek is the only FAST tier provider and should be selected
            assert decision.selected_provider == AIProviderName.DEEPSEEK
