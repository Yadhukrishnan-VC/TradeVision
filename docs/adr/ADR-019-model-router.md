# ADR-019: Model Router — Deterministic Provider Selection

**Status:** Proposed
**Date:** 2026-07-26
**Author:** Architecture Authority (Intelligence Domain)
**Product:** TradeVision AI
**Depends on:** ADR-015 (DeepSeek Provider), ADR-018 (Intelligence Domain Boundaries), `core/resilience/circuit_breaker.py` (reused, not rebuilt)

## Context

Five `BaseAIProvider` implementations now exist (Gemini, OpenAI, Claude, Ollama, DeepSeek), all at Phase 0 scope. ADR-017 (Strategy Registry) already references a `ModelRouter` that a matched strategy can override via `preferred_provider` — but no ModelRouter specification exists.

## Decision

### 1. Ownership

`ModelRouter` lives in `apps/ai_engine/model_router.py` — inside `ai_engine`, not a new app. Its single responsibility: **given a reasoning request's requirements, deterministically select which provider and model should serve it, and produce an ordered fallback chain.** Nothing else.

**It must never:**
- Render or construct prompts (that's `PromptManager`, ADR-016)
- Read or write Trader Memory
- Match or evaluate strategies (it only *consumes* a strategy's `preferred_provider` hint)
- Compute confidence scores (that's `recommendations`)
- Make or influence trade/execution decisions
- Call Trading Core in any direction

### 2. Inputs — `RoutingRequest`

```python
@dataclass(frozen=True)
class RoutingRequest:
    event_type: EventType
    required_capabilities: RoutingCapabilityRequirements
    context_tokens_estimate: int
    latency_budget_ms: int | None = None
    cost_budget_usd: Decimal | None = None
    preferred_provider: AIProviderName | None = None
    user_override_provider: AIProviderName | None = None
```

```python
@dataclass(frozen=True)
class RoutingCapabilityRequirements:
    requires_structured_json: bool = True
    requires_streaming: bool = False
    requires_vision: bool = False
    requires_function_calling: bool = False
```

### 3. Outputs — `RoutingDecision`

```python
@dataclass(frozen=True)
class RoutingDecision:
    selected_provider: AIProviderName
    selected_model: str
    rationale: str
    fallback_chain: tuple[AIProviderName, ...]
    routing_metadata: RoutingMetadata
```

```python
@dataclass(frozen=True)
class RoutingMetadata:
    candidates_considered: tuple[AIProviderName, ...]
    excluded: dict[str, str]
    circuit_states: dict[str, str]
```

### 4. Provider Capabilities

A concrete (non-abstract) method on `BaseAIProvider`:

```python
def capabilities(self) -> ProviderCapabilities:
    return ProviderCapabilities()
```

This does **not** touch the four existing abstract methods and does not require any existing provider to be modified.

### 5. Routing Policy (deterministic, in priority order)

1. User override — if set and circuit not OPEN, select it.
2. Capability filter — exclude providers whose capabilities don't satisfy requirements.
3. Health filter — exclude providers whose circuit breaker is OPEN. HALF_OPEN allowed.
4. Strategy preference — if `preferred_provider` survives filters, select it.
5. Cost filter — exclude providers whose cost tier exceeds budget.
6. Latency filter — if budget is tight, prefer FAST tier.
7. Default priority order — remaining candidates ranked by `AI_PROVIDER_PRIORITY`.
8. Selection — first candidate after steps 1-7.
9. No candidates — raise `NoAvailableProviderError`.

### 6. Failure Behavior

- No retries inside ModelRouter. Retry is each provider's concern inside `complete()` (Phase 4).
- Routing never calls a live provider — reads only circuit state from Redis.
- `"degraded"` does not exclude — only OPEN circuit does.
- Manual disablement via `AI_PROVIDER_DISABLED` setting.

## Consequences

1. `BaseAIProvider` gains one new concrete method (`capabilities()`) — additive, non-abstract, zero impact on existing providers.
2. One new exception class (`NoAvailableProviderError`).
3. ModelRouter has no dependency on `complete()` — buildable and testable now.
4. Real cost estimation is Phase 4.

## Implementation Notes

- New enums: `LatencyTier`, `CostTier` in `core/constants.py`.
- New settings: `AI_PROVIDER_PRIORITY`, `AI_PROVIDER_DISABLED`, `AI_ROUTING_FAST_TIER_THRESHOLD_MS`.
- `CircuitBreakerFactory` reused via constructor injection.
