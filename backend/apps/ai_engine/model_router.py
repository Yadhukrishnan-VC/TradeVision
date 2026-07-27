"""
TradeVision AI — Model Router.

Deterministic AI provider selection. See ADR-019.

Single responsibility: given a reasoning request's requirements,
deterministically select which provider and model should serve it,
and produce an ordered fallback chain.

ModelRouter never:
  - Renders or constructs prompts (that's PromptManager, ADR-016)
  - Reads or writes Trader Memory
  - Matches or evaluates strategies (it only consumes a strategy's
    preferred_provider hint)
  - Computes confidence scores
  - Calls any provider's complete(), validate_connection(), or health_check()
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any

from core.ai.base_provider import ProviderCapabilities
from core.ai.exceptions import NoAvailableProviderError
from core.config import config
from core.constants import AIProviderName, CostTier, LatencyTier
from core.events.event_types import EventType
from core.resilience.circuit_breaker import CircuitBreakerFactory, CircuitState

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Static provider capability table
# ---------------------------------------------------------------------------

PROVIDER_CAPABILITIES: dict[AIProviderName, ProviderCapabilities] = {
    AIProviderName.CLAUDE: ProviderCapabilities(
        supports_structured_json=True,
        supports_streaming=True,
        supports_vision=True,
        supports_function_calling=True,
        context_window_tokens=200000,
        max_output_tokens=8192,
        latency_tier=LatencyTier.STANDARD,
        cost_tier=CostTier.HIGH,
    ),
    AIProviderName.GEMINI: ProviderCapabilities(
        supports_structured_json=True,
        supports_streaming=True,
        supports_vision=True,
        supports_function_calling=True,
        context_window_tokens=1000000,
        max_output_tokens=8192,
        latency_tier=LatencyTier.STANDARD,
        cost_tier=CostTier.MEDIUM,
    ),
    AIProviderName.DEEPSEEK: ProviderCapabilities(
        supports_structured_json=True,
        supports_streaming=True,
        supports_vision=False,
        supports_function_calling=False,
        context_window_tokens=128000,
        max_output_tokens=4096,
        latency_tier=LatencyTier.FAST,
        cost_tier=CostTier.LOW,
    ),
    AIProviderName.OPENAI: ProviderCapabilities(
        supports_structured_json=True,
        supports_streaming=True,
        supports_vision=True,
        supports_function_calling=True,
        context_window_tokens=128000,
        max_output_tokens=4096,
        latency_tier=LatencyTier.STANDARD,
        cost_tier=CostTier.MEDIUM,
    ),
    AIProviderName.OLLAMA: ProviderCapabilities(
        supports_structured_json=True,
        supports_streaming=False,
        supports_vision=False,
        supports_function_calling=False,
        context_window_tokens=8192,
        max_output_tokens=4096,
        latency_tier=LatencyTier.SLOW,
        cost_tier=CostTier.FREE,
    ),
}
"""Static capability profiles for every supported AI provider.

These are known, fixed properties of each model — not queried live.
Placeholder values are acceptable for providers not yet in active use,
but every provider must be present in this table.
"""


# ---------------------------------------------------------------------------
# Request / Response dataclasses
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class RoutingCapabilityRequirements:
    """Required capabilities for a routing request.

    All fields default to ``False`` except ``requires_structured_json``
    which is ``True`` by default (the AI Brain always outputs JSON).
    """

    requires_structured_json: bool = True
    requires_streaming: bool = False
    requires_vision: bool = False
    requires_function_calling: bool = False


@dataclass(frozen=True)
class RoutingRequest:
    """Input to ``ModelRouter.route()``.

    Callers extract only what routing needs from the IntelligencePacket —
    never pass the full packet to the router.
    """

    event_type: EventType
    required_capabilities: RoutingCapabilityRequirements = field(
        default_factory=RoutingCapabilityRequirements
    )
    context_tokens_estimate: int = 0
    latency_budget_ms: int | None = None
    cost_budget_usd: Decimal | None = None
    preferred_provider: AIProviderName | None = None
    user_override_provider: AIProviderName | None = None


@dataclass(frozen=True)
class RoutingMetadata:
    """Diagnostic metadata attached to each ``RoutingDecision``."""

    candidates_considered: tuple[AIProviderName, ...] = ()
    excluded: dict[str, str] = field(default_factory=dict)
    circuit_states: dict[str, str] = field(default_factory=dict)


@dataclass(frozen=True)
class RoutingDecision:
    """Output of ``ModelRouter.route()``.

    Contains the selected provider, its model name, a human-readable
    rationale, an ordered fallback chain, and diagnostic metadata.
    """

    selected_provider: AIProviderName
    selected_model: str
    rationale: str
    fallback_chain: tuple[AIProviderName, ...] = ()
    routing_metadata: RoutingMetadata = field(default_factory=RoutingMetadata)


# ---------------------------------------------------------------------------
# Model Router
# ---------------------------------------------------------------------------


class ModelRouter:
    """Deterministic AI provider selection.

    Does not call any provider. Reads circuit state from Redis (via the
    injected ``CircuitBreakerFactory``) and static capability/priority
    configuration only.

    Args:
        circuit_breaker_factory: Shared ``CircuitBreakerFactory`` instance
            (injected, never instantiated ad hoc inside ModelRouter).
    """

    def __init__(self, circuit_breaker_factory: CircuitBreakerFactory) -> None:
        self._cb_factory = circuit_breaker_factory

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def route(self, request: RoutingRequest) -> RoutingDecision:
        """Apply the 9-step routing policy (ADR-019 §5).

        Steps:
            1. User override — highest precedence.
            2. Capability filter — exclude providers missing requirements.
            3. Health filter — exclude OPEN circuits.
            4. Strategy preference — use ``preferred_provider`` if healthy.
            5. Cost filter — exclude providers above budget.
            6. Latency filter — prefer FAST tier when budget is tight.
            7. Default priority order — rank by ``AI_PROVIDER_PRIORITY``.
            8. Selection — first remaining candidate.
            9. No candidates — raise ``NoAvailableProviderError``.

        Returns:
            A ``RoutingDecision`` with the selected provider and fallback chain.

        Raises:
            NoAvailableProviderError: If every candidate is excluded.
        """
        all_providers: list[AIProviderName] = list(AIProviderName)
        excluded: dict[str, str] = {}
        circuit_states: dict[str, str] = {}

        # Step 1: User override
        override = request.user_override_provider
        if override is not None:
            override_state = self._circuit_state(override)
            circuit_states[override.value] = override_state.value
            if override_state != CircuitState.OPEN:
                provider = override
                excluded.update(self._exclude_others(provider, all_providers))
                fallback_excluded = self._compute_route_exclusions(
                    all_providers, circuit_states, request
                )
                fallback = self._build_fallback(
                    provider,
                    all_providers,
                    fallback_excluded,
                    circuit_states,
                    request,
                )
                return RoutingDecision(
                    selected_provider=provider,
                    selected_model=provider.value,
                    rationale=f"User override: {provider.value} (circuit={override_state.value})",
                    fallback_chain=fallback,
                    routing_metadata=RoutingMetadata(
                        candidates_considered=tuple(all_providers),
                        excluded=excluded,
                        circuit_states=circuit_states,
                    ),
                )
            excluded[override.value] = f"circuit is {override_state.value}"

        # Step 2: Capability filter
        for prov in all_providers:
            caps = PROVIDER_CAPABILITIES.get(prov, ProviderCapabilities())
            reason = self._capability_filter_reason(prov, caps, request)
            if reason:
                excluded[prov.value] = reason

        # Step 3: Health filter (circuit state + manual disable)
        disabled = config.ai_provider_disabled
        for prov in all_providers:
            if prov.value in excluded:
                continue
            if prov.value in disabled:
                excluded[prov.value] = "manually disabled via AI_PROVIDER_DISABLED"
                continue
            state = self._circuit_state(prov)
            circuit_states[prov.value] = state.value
            if state == CircuitState.OPEN:
                excluded[prov.value] = "circuit breaker is OPEN"

        # Step 4: Strategy preference
        preferred = request.preferred_provider
        if preferred is not None and preferred.value not in excluded:
            fallback = self._build_fallback(
                preferred, all_providers, excluded, circuit_states, request
            )
            return RoutingDecision(
                selected_provider=preferred,
                selected_model=preferred.value,
                rationale=f"Strategy preference: {preferred.value}",
                fallback_chain=fallback,
                routing_metadata=RoutingMetadata(
                    candidates_considered=tuple(all_providers),
                    excluded=excluded,
                    circuit_states=circuit_states,
                ),
            )

        # Step 5: Cost filter
        cost_budget = request.cost_budget_usd
        if cost_budget is not None:
            ceilings = config.ai_cost_tier_ceilings
            for prov in all_providers:
                if prov.value in excluded:
                    continue
                caps = PROVIDER_CAPABILITIES.get(prov, ProviderCapabilities())
                ceiling_str = ceilings.get(caps.cost_tier.value, "0.000")
                if Decimal(ceiling_str) > cost_budget:
                    excluded[prov.value] = (
                        f"cost tier {caps.cost_tier.value} exceeds "
                        f"budget ${cost_budget:.3f}"
                    )

        # Step 6: Latency filter
        budget_ms = request.latency_budget_ms
        tight_latency = (
            budget_ms is not None
            and budget_ms < config.ai_routing_fast_tier_threshold_ms
        )
        if tight_latency:
            for prov in all_providers:
                if prov.value in excluded:
                    continue
                caps = PROVIDER_CAPABILITIES.get(prov, ProviderCapabilities())
                if caps.latency_tier != LatencyTier.FAST:
                    excluded[prov.value] = (
                        f"latency tier {caps.latency_tier.value} does not meet "
                        f"tight budget of {budget_ms}ms"
                    )

        # Step 7-8: Default priority order + selection
        priority = config.ai_provider_priority
        candidates = [p for p in priority if p not in excluded]
        valid_candidates: list[AIProviderName] = []
        for name in candidates:
            try:
                valid_candidates.append(AIProviderName(name))
            except ValueError:
                continue

        if not valid_candidates:
            # Step 9: No candidates
            metadata = RoutingMetadata(
                candidates_considered=tuple(all_providers),
                excluded=excluded,
                circuit_states=circuit_states,
            )
            raise NoAvailableProviderError(
                f"No AI provider available after routing policy filters. "
                f"Excluded: {excluded}. "
                "Check provider configuration, circuit states, and budget settings."
            )

        selected = valid_candidates[0]
        remaining = valid_candidates[1:]

        return RoutingDecision(
            selected_provider=selected,
            selected_model=selected.value,
            rationale=f"Routed by priority: {selected.value} (position {priority.index(selected.value) + 1} of {len(priority)})",
            fallback_chain=tuple(remaining),
            routing_metadata=RoutingMetadata(
                candidates_considered=tuple(all_providers),
                excluded=excluded,
                circuit_states=circuit_states,
            ),
        )

    def next_in_chain(
        self,
        decision: RoutingDecision,
        failed_provider: AIProviderName,
    ) -> AIProviderName | None:
        """Return the next provider after ``failed_provider``.

        If ``failed_provider`` is the ``decision.selected_provider``,
        the first entry in ``fallback_chain`` is returned.
        If ``failed_provider`` is itself in ``fallback_chain``, the
        *following* entry is returned.
        Returns ``None`` when the chain is exhausted.

        Pure function — does not re-run routing or touch circuit state.
        The caller is responsible for reporting the failure to the circuit
        breaker via the existing ``CircuitBreaker.record_failure()``.
        """
        chain = decision.fallback_chain
        if not chain:
            return None

        # The selected provider failed — return the first fallback
        if failed_provider == decision.selected_provider:
            return chain[0]

        # A fallback provider failed — return the next one in chain
        if failed_provider in chain:
            idx = chain.index(failed_provider)
            next_idx = idx + 1
            if next_idx < len(chain):
                return chain[next_idx]

        return None

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _circuit_state(self, provider: AIProviderName) -> CircuitState:
        """Read the current circuit state for a provider."""
        breaker = self._cb_factory.get_or_create(f"ai-provider-{provider.value}")
        return breaker.state

    def _capability_filter_reason(
        self,
        provider: AIProviderName,
        caps: ProviderCapabilities,
        request: RoutingRequest,
    ) -> str | None:
        """Return an exclusion reason if ``provider`` lacks required capabilities."""
        req = request.required_capabilities

        if req.requires_structured_json and not caps.supports_structured_json:
            return "does not support structured JSON output"
        if req.requires_streaming and not caps.supports_streaming:
            return "does not support streaming"
        if req.requires_vision and not caps.supports_vision:
            return "does not support vision"
        if req.requires_function_calling and not caps.supports_function_calling:
            return "does not support function calling"

        if request.context_tokens_estimate > caps.context_window_tokens:
            return (
                f"context window ({caps.context_window_tokens}) too small "
                f"for estimated {request.context_tokens_estimate} tokens"
            )

        return None

    def _compute_route_exclusions(
        self,
        all_providers: list[AIProviderName],
        circuit_states: dict[str, str],
        request: RoutingRequest,
    ) -> dict[str, str]:
        """Apply capability, health, cost, and latency filters.

        Returns an exclusion dict with reasons for every provider that
        does not qualify.  Used by the override path to build a fallback
        chain from the *real* candidate set.
        """
        result: dict[str, str] = {}

        # Capability filter
        for prov in all_providers:
            caps = PROVIDER_CAPABILITIES.get(prov, ProviderCapabilities())
            reason = self._capability_filter_reason(prov, caps, request)
            if reason:
                result[prov.value] = reason

        # Health filter (circuit state + manual disable)
        disabled = config.ai_provider_disabled
        for prov in all_providers:
            if prov.value in result:
                continue
            if prov.value in disabled:
                result[prov.value] = "manually disabled via AI_PROVIDER_DISABLED"
                continue
            state = self._circuit_state(prov)
            if prov.value not in circuit_states:
                circuit_states[prov.value] = state.value
            if state == CircuitState.OPEN:
                result[prov.value] = "circuit breaker is OPEN"

        # Cost filter
        cost_budget = request.cost_budget_usd
        if cost_budget is not None:
            ceilings = config.ai_cost_tier_ceilings
            for prov in all_providers:
                if prov.value in result:
                    continue
                caps = PROVIDER_CAPABILITIES.get(prov, ProviderCapabilities())
                ceiling_str = ceilings.get(caps.cost_tier.value, "0.000")
                if Decimal(ceiling_str) > cost_budget:
                    result[prov.value] = (
                        f"cost tier {caps.cost_tier.value} exceeds "
                        f"budget ${cost_budget:.3f}"
                    )

        # Latency filter
        budget_ms = request.latency_budget_ms
        tight_latency = (
            budget_ms is not None
            and budget_ms < config.ai_routing_fast_tier_threshold_ms
        )
        if tight_latency:
            for prov in all_providers:
                if prov.value in result:
                    continue
                caps = PROVIDER_CAPABILITIES.get(prov, ProviderCapabilities())
                if caps.latency_tier != LatencyTier.FAST:
                    result[prov.value] = (
                        f"latency tier {caps.latency_tier.value} does not meet "
                        f"tight budget of {budget_ms}ms"
                    )

        return result

    def _exclude_others(
        self,
        selected: AIProviderName,
        all_providers: list[AIProviderName],
    ) -> dict[str, str]:
        """Build an exclusion dict labelling all providers except the selected one."""
        result: dict[str, str] = {}
        for prov in all_providers:
            if prov != selected:
                result[prov.value] = f"overridden by user choice: {selected.value}"
        return result

    def _build_fallback(
        self,
        selected: AIProviderName,
        all_providers: list[AIProviderName],
        excluded: dict[str, str],
        circuit_states: dict[str, str],
        request: RoutingRequest,
    ) -> tuple[AIProviderName, ...]:
        """Build a fallback chain from remaining non-excluded providers in priority order."""
        priority = config.ai_provider_priority
        remaining: list[AIProviderName] = []
        for name in priority:
            if name == selected.value:
                continue
            if name in excluded:
                continue
            try:
                remaining.append(AIProviderName(name))
            except ValueError:
                continue
        return tuple(remaining)
