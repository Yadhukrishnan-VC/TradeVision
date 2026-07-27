# ADR-020: Model Router — Provider-Preference Enhancement

**Status:** Draft
**Date:** 2026-07-27
**Deciders:** Principal AI Architect (Intelligence domain)

## Context

ADR-019 defined a 9-step deterministic routing policy. Batch B introduces `TradingStrategy.preferred_provider`, a hint from Strategy Registry about which provider to prefer for a given strategy.

## Decision

1. `preferred_provider` is inserted into `RoutingRequest` and evaluated **before** capability/health batch filters (moved from Step 4 to Step 1a).
2. Individual capability and circuit-breaker checks still apply — a preference is a hint, never an override.
3. `RoutingDecision` gains `decision_trace: tuple[str, ...]` for observability.
4. Provider capability tables and cost/latency tiers are readable from `core.config` at call time, enabling hot-reload without code deploy.

## Consequences

- Callers that never set `preferred_provider` see zero behavior change.
- Existing 8 test classes pass unmodified.
- Operators can adjust cost tiers via env var without redeploy.
