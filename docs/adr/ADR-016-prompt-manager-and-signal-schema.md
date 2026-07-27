# ADR-016: Prompt Manager and Signal Schema

**Status:** DRAFT  
**Date:** 2026-07-26  
**Owner:** Principal AI Architect  
**Depends on:** ADR-018

## Context

The AI needs structured, versioned prompt templates and a new response vocabulary (BUY, SELL, WAIT, EXIT, REDUCE) that is separate from the existing `RecommendationDirection` enum.

## Decision

### 1. Prompt Template System

Rewrite the empty `core/ai/prompts/` Jinja2 templates into a structured system:

- `base.j2` — shared system prompt, instructions, and output format specification
- One specialised template per `EventType` value (8 total)
- Each template inherits `base.j2` and adds event-specific emphasis instructions
- Templates are rendered by `PromptManager` which injects context blocks

### 2. PromptManager Service

New module `apps/ai_engine/prompt_manager/` containing:

- `PromptManager` — template loading, versioning, rendering
- `IntelligenceResponseSchema` — Pydantic v2 model for AI output validation
- Template version tracked by content hash + explicit `VERSION` comment

### 3. Context Blocks

Every prompt includes these sections, injected by `PromptManager.render()`:

1. `PINE_OUTPUT` — indicator values from Pine Script (passed verbatim)
2. `MARKET_REGIME` — current regime classification (deterministic)
3. `MULTI_TIMEFRAME` — alignment across daily/weekly/hourly (deterministic)
4. `NEWS` — relevant headlines with sentiment
5. `SECTOR_CONTEXT` — sector performance
6. `PORTFOLIO_STATE` — current positions if applicable
7. `RISK_STATE` — current risk metrics
8. `TRADING_HISTORY` — recent similar recommendations and outcomes

### 4. Response Schema

The AI must output JSON conforming to `IntelligenceResponseSchema`:

```json
{
    "signal": "BUY|SELL|WAIT|EXIT|REDUCE",
    "confidence_score": 0.0-1.0,
    "reasoning": "...",
    "trade_explanation": "...",
    "risk_level": "LOW|MEDIUM|HIGH|VERY_HIGH",
    "risk_explanation": "...",
    "key_factors": ["..."],
    "contradicting_factors": ["..."],
    "time_horizon": "INTRADAY|SHORT|MEDIUM|LONG",
    "follow_up_triggers": ["..."],
    "market_regime_assessment": "BULLISH_TREND|BEARISH_TREND|RANGING|VOLATILE|BREAKOUT|BREAKDOWN",
    "multi_timeframe_alignment": "ALIGNED|CONFLICTING|NEUTRAL",
    "data_quality_note": "..."
}
```

## Consequences

- Prompt templates are versioned and auditable via Trader Memory
- Response schema is validated by Pydantic before any business logic runs
- Template changes are tracked and version-tagged in Trader Memory records
- New response vocabulary (BUY, SELL, WAIT, EXIT, REDUCE) does not affect existing `core.constants`
