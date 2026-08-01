# ADR-007: Pattern Engine — Phase 6 (Historical Session Similarity)

**Status:** Approved
**Date:** 2026-07-31
**Author:** Architecture Authority
**Product:** TradeVision AI

## Context

The Pattern Engine must find historical trading days that are structurally similar to the current `IntelligencePacket` for a symbol, score them deterministically, and hand the AI real historical analogues — never speculation. It must not call any LLM, must not recompute indicators already produced by Technical Analysis, and must not mutate MarketContext, Rule Engine, or Trading Core.

## Decision

**Implement a deterministic, packet-scoped similarity engine in the `pattern_engine` app.** It subscribes to `intelligence.PacketBuilt` (the only stream that carries the full packet; `rule_engine.RuleFired` carries only symbol/rule metadata) and publishes `pattern_engine.PatternAnalysisCompleted`.

### Similarity scoring

Weighted group distances per the frozen table:

| Feature Group | Features Used | Weight |
|---|---|---|
| Price action | Change %, gap %, volume ratio | 30% |
| Technical state | RSI, MACD histogram, BB position, trend | 25% |
| Options | PCR, OI change direction | 15% |
| Macro/Global | Nifty %, crude %, FII net flow direction | 20% |
| Breadth | Sector trend direction, A/D ratio | 10% |

Overall similarity is `1 - weighted normalized distance`, clamped to `[0, 1]`. Historical sessions below `PATTERN_ENGINE_MIN_SIMILARITY` (default `0.60`) are excluded; the top `PATTERN_ENGINE_TOP_N` (default `5`) are returned.

### Event contract

The published payload keeps the exact shape consumed by the frozen `apps.intelligence` handler: `symbol`, `similar_dates[{date_str, similarity_score, outcome_summary}]`, `top_analogue_summary`. Additive keys (`run_id`, `feature_distance`, `matching_patterns`, `historical_recommendation_accuracy`, `confidence_contribution`, `evidence`, `data_sufficiency_note`) are appended without altering the contract.

### Trader Memory enrichment

Historical recommendation accuracy is resolved from Trader Memory only when `PATTERN_ENGINE_ACCURACY_LOOKUP_ENABLED` is set (default `False`). A lookup failure degrades to `None` and never propagates.

## Consequences

1. **Feature vector duplication is intentional**: historical vectors are stored in `pattern_engine` (not market_data) because they combine TA output with packet context into one snapshot; the similarity math is a pure function over feature vectors.
2. **Trigger parity with the rule engine**: both consume `intelligence.PacketBuilt`, so pattern analysis runs whenever a fresh packet is built and is disabled by default (`PATTERN_ENGINE_ENABLED`, default `False`).
3. **No direction/signal fields**: the Pattern Engine scores and describes history; it never emits BUY/SELL/signal/direction.
4. **Failure tolerance**: any exception in the handler or enrichment path is logged and swallowed so the packet pipeline is never broken.

## Implementation Notes

- Celery tasks (`run_pattern_analysis`, `precompute_historical_vectors`) run on the `analytics` queue using `BaseTask`.
- `EventBusService.register_all_handlers()` auto-discovers `apps.pattern_engine.infrastructure.event_handlers.register_handlers`.
- Backfill (`precompute_historical_vectors`) builds historical vectors from market_data candles/TA snapshots and computes 24h outcomes.
