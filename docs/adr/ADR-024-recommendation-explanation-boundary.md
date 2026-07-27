# ADR-024: Recommendation Explanation Boundary

**Status:** Draft
**Date:** 2026-07-27
**Deciders:** Principal AI Architect (Intelligence domain)

## Context

`apps.recommendations` was an empty scaffold. The LLM already produces `trade_explanation` and `risk_explanation` fields in validated output. Batch B adds an `ExplanationComposer` that consumes (does not regenerate) these fields and appends deterministic context (confidence adjustments, strategy thresholds).

## Decision

1. `ExplanationComposer.compose()` concatenates the raw LLM explanations with confidence adjustment reasons and strategy metadata.
2. `compose_fallback()` provides a simple concatenation when the composer fails — never blocks recommendation issuance.
3. `RecommendationExplanation` model persists one record per issued recommendation.
4. Boundary rule from ADR-018 holds: only `RecommendationDirection` (BUY/SELL/WATCH/AVOID) crosses into Trading Core. No `IntelligenceSignal` value ever appears on a `RECOMMENDATION_EXPLAINED` or `RECOMMENDATION_ISSUED` event payload.
5. The composed explanation is additive — existing consumers of `trade_explanation`/`risk_explanation` see no change.

## Consequences

- Existing code referencing raw explanation fields continues to work unchanged.
- Recommendation issuance is never blocked by explanation composition failure.
- The Trading Core boundary remains clean (no `IntelligenceSignal` leakage).
