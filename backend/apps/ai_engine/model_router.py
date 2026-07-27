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


@dataclass(frozen=True)
class RoutingCapabilityRequirements:
    requires_structured_json: bool = True
    requires_streaming: bool = False
    requires_vision: bool = False
    requires_function_calling: bool = False


@dataclass(frozen=True)
class RoutingRequest:
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
    candidates_considered: tuple[AIProviderName, ...] = ()
    excluded: dict[str, str] = field(default_factory=dict)
    circuit_states: dict[str, str] = field(default_factory=dict)


@dataclass(frozen=True)
class RoutingDecision:
    selected_provider: AIProviderName
    selected_model: str
    rationale: str
    fallback_chain: tuple[AIProviderName, ...] = ()
    routing_metadata: RoutingMetadata = field(default_factory=RoutingMetadata)
    decision_trace: tuple[str, ...] = ()


class ModelRouter:
    def __init__(self, circuit_breaker_factory: CircuitBreakerFactory) -> None:
        self._cb_factory = circuit_breaker_factory

    def get_provider_capabilities(self) -> dict[AIProviderName, ProviderCapabilities]:
        return PROVIDER_CAPABILITIES

    def route(self, request: RoutingRequest) -> RoutingDecision:
        all_providers: list[AIProviderName] = list(AIProviderName)
        excluded: dict[str, str] = {}
        circuit_states: dict[str, str] = {}
        trace: list[str] = []

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
                trace.append(f"Step 1: User override {provider.value}")
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
                    decision_trace=tuple(trace),
                )
            excluded[override.value] = f"circuit is {override_state.value}"
            trace.append(f"Step 1: User override {override.value} excluded (circuit OPEN)")

        preferred = request.preferred_provider
        if preferred is not None:
            caps_map = self.get_provider_capabilities()
            preferred_caps = caps_map.get(preferred, ProviderCapabilities())
            cap_reason = self._capability_filter_reason(preferred, preferred_caps, request)
            circuit_state = self._circuit_state(preferred)
            circuit_states[preferred.value] = circuit_state.value

            if cap_reason:
                excluded[preferred.value] = cap_reason
                trace.append(
                    f"Step 1a: Preferred {preferred.value} excluded (capability: {cap_reason})"
                )
            elif circuit_state == CircuitState.OPEN:
                excluded[preferred.value] = "circuit breaker is OPEN"
                trace.append(
                    f"Step 1a: Preferred {preferred.value} excluded (circuit OPEN)"
                )
            elif preferred.value in config.ai_provider_disabled:
                excluded[preferred.value] = "manually disabled via AI_PROVIDER_DISABLED"
                trace.append(
                    f"Step 1a: Preferred {preferred.value} excluded (manually disabled)"
                )
            else:
                fallback_excluded = self._compute_route_exclusions(
                    all_providers, circuit_states, request
                )
                fallback = self._build_fallback(
                    preferred,
                    all_providers,
                    fallback_excluded,
                    circuit_states,
                    request,
                )
                trace.append(
                    f"Step 1a: Preferred {preferred.value} passes capability/circuit checks"
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
                    decision_trace=tuple(trace),
                )

        caps_map = self.get_provider_capabilities()
        for prov in all_providers:
            caps = caps_map.get(prov, ProviderCapabilities())
            reason = self._capability_filter_reason(prov, caps, request)
            if reason:
                excluded[prov.value] = reason
        trace.append(
            f"Step 2: Capability filter — {len([k for k in excluded if 'does not support' in excluded[k] or 'context window' in excluded[k]])} excluded"
        )

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
        trace.append(
            f"Step 3: Health filter — {len([k for k in excluded if 'circuit' in excluded[k] or 'disabled' in excluded[k]])} excluded"
        )

        cost_budget = request.cost_budget_usd
        if cost_budget is not None:
            ceilings = config.ai_cost_tier_ceilings
            for prov in all_providers:
                if prov.value in excluded:
                    continue
                caps = caps_map.get(prov, ProviderCapabilities())
                ceiling_str = ceilings.get(caps.cost_tier.value, "0.000")
                if Decimal(ceiling_str) > cost_budget:
                    excluded[prov.value] = (
                        f"cost tier {caps.cost_tier.value} exceeds "
                        f"budget ${cost_budget:.3f}"
                    )
            trace.append(
                f"Step 4: Cost filter — {len([k for k in excluded if 'cost' in excluded[k]])} excluded"
            )
        else:
            trace.append("Step 4: Cost filter — skipped (no budget set)")

        budget_ms = request.latency_budget_ms
        tight_latency = (
            budget_ms is not None
            and budget_ms < config.ai_routing_fast_tier_threshold_ms
        )
        if tight_latency:
            for prov in all_providers:
                if prov.value in excluded:
                    continue
                caps = caps_map.get(prov, ProviderCapabilities())
                if caps.latency_tier != LatencyTier.FAST:
                    excluded[prov.value] = (
                        f"latency tier {caps.latency_tier.value} does not meet "
                        f"tight budget of {budget_ms}ms"
                    )
            trace.append(
                f"Step 5: Latency filter — {len([k for k in excluded if 'latency' in excluded[k]])} excluded"
            )
        else:
            trace.append("Step 5: Latency filter — skipped (no tight budget)")

        priority = config.ai_provider_priority
        candidates = [p for p in priority if p not in excluded]
        valid_candidates: list[AIProviderName] = []
        for name in candidates:
            try:
                valid_candidates.append(AIProviderName(name))
            except ValueError:
                continue

        trace.append(
            f"Step 6: Priority order — {len(valid_candidates)} candidate(s) after filtering: "
            f"{[v.value for v in valid_candidates]}"
        )

        if not valid_candidates:
            trace.append("Step 7: No candidates available — raising NoAvailableProviderError")
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
        trace.append(f"Step 8: Selected {selected.value}, fallback chain: {[r.value for r in remaining]}")

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
            decision_trace=tuple(trace),
        )

    def next_in_chain(
        self,
        decision: RoutingDecision,
        failed_provider: AIProviderName,
    ) -> AIProviderName | None:
        chain = decision.fallback_chain
        if not chain:
            return None

        if failed_provider == decision.selected_provider:
            return chain[0]

        if failed_provider in chain:
            idx = chain.index(failed_provider)
            next_idx = idx + 1
            if next_idx < len(chain):
                return chain[next_idx]

        return None

    def _circuit_state(self, provider: AIProviderName) -> CircuitState:
        breaker = self._cb_factory.get_or_create(f"ai-provider-{provider.value}")
        return breaker.state

    def _capability_filter_reason(
        self,
        provider: AIProviderName,
        caps: ProviderCapabilities,
        request: RoutingRequest,
    ) -> str | None:
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
        result: dict[str, str] = {}
        caps_map = self.get_provider_capabilities()

        for prov in all_providers:
            caps = caps_map.get(prov, ProviderCapabilities())
            reason = self._capability_filter_reason(prov, caps, request)
            if reason:
                result[prov.value] = reason

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

        cost_budget = request.cost_budget_usd
        if cost_budget is not None:
            ceilings = config.ai_cost_tier_ceilings
            for prov in all_providers:
                if prov.value in result:
                    continue
                caps = caps_map.get(prov, ProviderCapabilities())
                ceiling_str = ceilings.get(caps.cost_tier.value, "0.000")
                if Decimal(ceiling_str) > cost_budget:
                    result[prov.value] = (
                        f"cost tier {caps.cost_tier.value} exceeds "
                        f"budget ${cost_budget:.3f}"
                    )

        budget_ms = request.latency_budget_ms
        tight_latency = (
            budget_ms is not None
            and budget_ms < config.ai_routing_fast_tier_threshold_ms
        )
        if tight_latency:
            for prov in all_providers:
                if prov.value in result:
                    continue
                caps = caps_map.get(prov, ProviderCapabilities())
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
