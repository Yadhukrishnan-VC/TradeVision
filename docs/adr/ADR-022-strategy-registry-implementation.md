# ADR-022: Strategy Registry (Implementation)

**Status:** Draft
**Date:** 2026-07-27
**Deciders:** Principal AI Architect (Intelligence domain)

## Context

ADR-017 defined the Strategy Registry concept as a doc-only ADR. Batch B implements it: a `TradingStrategy` model with symbol/sector filters, deterministic matching, and per-strategy `preferred_provider`, `confidence_threshold`, and `risk_threshold`.

## Decision

1. `apps.strategy_registry` is a new Django app with `TradingStrategy` model (UUID pk, soft-delete per BaseModel).
2. `StrategyMatcher.match(packet)` filters active strategies by symbol/sector, evaluates in `priority` order, returns first match or `None`.
3. Only `ACTIVE` strategies are considered; `INACTIVE` and `RETIRED` are excluded.
4. `STRATEGY_REGISTRY_ENABLED` kill-switch defaults to `False`.
5. `TradingStrategy.preferred_provider` is consumed by Model Router (ADR-020) as a hint only.
6. `TradingStrategy.confidence_threshold` / `.risk_threshold` are consumed by Confidence Engine V2 (ADR-023).

## Consequences

- No AI call fires without a matched strategy (ADR-002 gating extended).
- No-match packets are logged and dropped silently — no error raised.
- Soft-delete preserves history per ADR-010.
