# ADR-023: Confidence Engine V2

**Status:** Draft
**Date:** 2026-07-27
**Deciders:** Principal AI Architect (Intelligence domain)

## Context

Today `confidence_score` is a raw, unvalidated LLM output field. Batch B introduces deterministic confidence adjustment that never mutates the raw score but augments it with strategy thresholds, data-quality penalties, and a placeholder for future trader-memory calibration.

## Decision

1. `ConfidenceEngine.evaluate()` produces a separate `adjusted_confidence` — the raw `confidence_score` remains immutable for audit.
2. Adjustments apply: (a) strategy threshold check (PASS/HOLD), (b) data-quality penalty if IntelligencePacket enrichment is missing/stale, (c) placeholder hook for future trader-memory calibration (no-op).
3. `ConfidenceResult` contains `{raw_confidence, adjusted_confidence, threshold_met, adjustment_reasons}`.
4. `ConfidenceEvaluation` model persists every evaluation for audit trail.
5. `CONFIDENCE_ENGINE_V2_ENABLED` kill-switch defaults to `False`.
6. Failure fallback: pipeline logs error and passes through raw score tagged with `["confidence_engine_unavailable"]` — never blocks a recommendation.

## Consequences

- Downstream consumers with kill-switch off see exactly today's behavior.
- The raw LLM confidence is never overwritten, enabling calibration analysis later.
- Future trader-memory calibration can hook into the placeholder without API changes to consumers.
