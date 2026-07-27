# ADR-014: Intelligence Packet V2 — Portfolio, Risk, and Regime Context Blocks

**Status:** DRAFT
**Date:** 2026-07-26
**Owner:** Principal AI Architect

## Context

The Intelligence Packet V1 (defined in `core/events/event_types.py`) carries price,
technical, and market context for a symbol. However, the AI Brain requires three
additional context blocks that are not per-symbol in nature:

1. **Market Regime** — the current macro market classification (trending, ranging,
   volatile, etc.) computed from index-level data.
2. **Portfolio State** — the user's current positions, exposure, and P&L, needed for
   risk-aware recommendations.
3. **Risk State** — the user's current risk metrics (drawdown, volatility, VaR, etc.)
   used to modulate confidence and veto high-risk recommendations.

## Decision

### 1. Market Regime Context (`MARKET_REGIME`)

Computed by `apps/intelligence/domain/market_regime.py` using a deterministic,
rule-based algorithm:

| Regime | Trigger |
|---|---|
| `BULLISH_TREND` | Nifty/Sensex > 20 DMA, ADX > 25, RSI(14) > 55 |
| `BEARISH_TREND` | Nifty/Sensex < 20 DMA, ADX > 25, RSI(14) < 45 |
| `RANGING` | ADX < 20, Bollinger Band width < 5% |
| `VOLATILE` | India VIX > 25, ATR(14) > 3% of price |
| `BREAKOUT` | Price breaks 20 DMA with volume > 1.5× average |
| `BREAKDOWN` | Price breaks below 20 DMA with volume > 1.5× average |

The regime is computed once per market session (pre-market, intraday every 15 min,
post-market) and cached in Redis. All AI prompts receive the current regime via
`MARKET_REGIME` context block.

### 2. Portfolio State Context (`PORTFOLIO_STATE`)

Injected into the prompt when the user has active positions. Contains:

- Total exposure (as % of portfolio value)
- Top 3 positions by value
- Unrealised P&L for the symbol being analysed
- Sector concentration (as % of portfolio per sector)
- Margin utilisation (if applicable)

This data is retrieved from `apps/portfolio/models.py` via `PortfolioService`
and masked (set to empty) when no active positions exist to avoid leaking
information.

### 3. Risk State Context (`RISK_STATE`)

Computed from the user's portfolio + position data:

| Metric | Source |
|---|---|
| Current drawdown % | PortfolioService |
| Portfolio volatility (30d) | Position-level returns |
| VaR (95%, 1d) | Historical simulation |
| Max position size vs. portfolio | PortfolioService |
| Leverage ratio | PortfolioService |

When any risk metric exceeds its configurable threshold, a `RISK_WARNING` flag is
attached to the prompt, and the AI response's confidence is modulated downward
by a deterministic formula in `core/ai/confidence.py`.

### 4. Injection Flow

```
IntelligencePacket (V1, per-symbol)
    + MARKET_REGIME (session-level, cached)
    + PORTFOLIO_STATE (user-level, masked when empty)
    + RISK_STATE (user-level, computed on demand)
    = PromptManager.render() → final prompt
```

All three context blocks are assembled by `PromptManager.render()` (see ADR-016)
and injected as structured sections in every AI prompt template.

## Consequences

- AI recommendations are risk-aware and portfolio-aware, not just symbol-aware
- Regime detection is deterministic (no LLM dependency for market classification)
- Portfolio/risk data is only injected when available — prompts gracefully degrade
  when the user has no positions
- Additional context blocks can be added in future ADRs without modifying existing
  block producers

## Dependencies

- None — this ADR defines the context contracts consumed by ADR-016 (Prompt Manager)

