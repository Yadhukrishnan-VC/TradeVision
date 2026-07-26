# ADR-017: Strategy Registry

**Status:** DRAFT  
**Date:** 2026-07-26  
**Owner:** Principal AI Architect  
**Depends on:** ADR-014, ADR-016

## Context

Different market conditions and user preferences require different trading strategies. The AI Brain needs a deterministic way to match incoming events to the appropriate strategy, which influences model selection, confidence thresholds, and risk parameters.

## Decision

### 1. TradingStrategy Model

Create `apps/strategy_registry/models.py` with fields:

| Field | Type | Purpose |
|---|---|---|
| `name` | CharField, unique | Strategy identifier |
| `description` | TextField | Human-readable description |
| `version` | CharField | Semantic version |
| `is_active` | BooleanField | Soft enable/disable |
| `preferred_provider` | CharField | Override model routing |
| `min_confidence_threshold` | FloatField | Per-strategy confidence floor |
| `max_risk_level` | CharField | Risk cap for this strategy |
| `included_sectors` | JSONField | Sector whitelist |
| `excluded_symbols` | JSONField | Symbol blacklist |
| `min_market_cap_cr` | FloatField | Minimum market cap filter |
| `active_timeframes` | JSONField | Timeframe filters |
| `preferred_horizon` | CharField | INTRADAY/SHORT/MEDIUM/LONG |

### 2. StrategyRegistry Service

Deterministic matching algorithm:

1. Query all active strategies
2. Filter by symbol filters (sector inclusion/exclusion, market cap)
3. Score remaining strategies by overlap with current market conditions
4. Return highest-scoring strategy (or `None`)

### 3. Model Routing Integration

When a strategy is matched and specifies `preferred_provider`, the `ModelRouter` (Batch E) attempts that provider first before falling through to the default routing table.

## Consequences

- Strategies are configurable via Django admin without code changes
- Model routing can be overridden per strategy without modifying routing logic
- Strategy performance can be tracked and compared via Trader Memory records
- Multiple strategies can coexist with different risk profiles
