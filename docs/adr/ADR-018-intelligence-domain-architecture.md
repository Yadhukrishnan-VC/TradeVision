# ADR-018: Intelligence Domain Architecture

**Status:** DRAFT  
**Date:** 2026-07-26  
**Owner:** Principal AI Architect

## Context

The Intelligence domain must extend the Phase 0 foundation to provide AI-powered reasoning while strictly respecting the existing Trading Core boundaries. The existing `IntelligencePacket` (defined in `core/events/event_types.py`) is the central context object, but the AI Brain needs richer input signals and new output vocabularies.

## Decision

### 1. Intelligence Domain Signal Types

Create `core/ai/signals.py` with `IntelligenceSignal` enum:

| Signal | Meaning |
|---|---|
| `BUY` | Strong conviction, favourable entry |
| `SELL` | Bearish conviction, exit or short |
| `WAIT` | Signal ambiguous, hold existing position |
| `EXIT` | Active position should be closed immediately |
| `REDUCE` | Reduce position size by half |

These are mapped to existing `RecommendationDirection` via `map_signal_to_recommendation()` — a pure translation function that is the only bridge to Trading Core enums.

### 2. Domain Boundaries

- Intelligence domain code lives in `apps/` (Django apps) and `core/ai/` (non-Django modules)
- `core/constants.py` only gains `AIProviderName.DEEPSEEK`
- No existing `BaseAIProvider` methods, `AIRequest`, `AIRawResponse`, or `AIRecommendation` are modified
- New response schema `IntelligenceResponseSchema` lives in `apps/ai_engine/prompt_manager/` — separate from `core/ai/validator.py`

### 3. Ground Rules

- AI NEVER computes technical indicators — Pine Script output is ingested via `PineOutput` model
- Market regime detection is deterministic (rule-based)
- Model routing is deterministic (rule-based lookup table)
- Confidence modifiers are deterministic (mathematical formula)
- News NLP is rule-based (lexicon + heuristics)

## Consequences

- Clean separation of concerns between Intelligence domain and Trading Core
- New signal types (WAIT, EXIT, REDUCE) available for AI output without breaking existing consumers
- All AI provider errors continue to map to the existing `core.ai.exceptions` hierarchy
- Trader Memory stores both domain signal and Trading Core direction for auditability

## Dependencies

- None from this ADR alone — it is the architectural foundation for ADR-015, ADR-016, ADR-017
