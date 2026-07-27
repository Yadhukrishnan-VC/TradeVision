# ADR-025: AI/Intelligence App Registration & Migration Baseline

**Status:** Draft
**Date:** 2026-07-27
**Deciders:** Principal AI Architect (Intelligence domain)

## Context

Repository audit found that `apps.ai_engine`, `apps.intelligence`, `apps.recommendations` have existing code but are not registered in `INSTALLED_APPS` and have no migrations. `apps.strategy_registry` does not exist. No AI/Intelligence app can run in the platform without registration and migrations.

## Decision

1. Add all four apps to `LOCAL_APPS` in `config/settings/base.py`: `apps.ai_engine`, `apps.intelligence`, `apps.recommendations`, `apps.strategy_registry`.
2. Create `AppConfig` classes for each with `ready()` calling `EventBusService.register_all_handlers()`.
3. Generate initial migrations for each app:
   - `ai_engine`: `PromptVersion`, `ConfidenceEvaluation`
   - `intelligence`: `PineOutput`
   - `recommendations`: `RecommendationExplanation`
   - `strategy_registry`: `TradingStrategy`
4. This is a prerequisite (B.0) — no Batch B item can be verified running until this merges.

## Consequences

- Django `check --deploy` passes — no more `models.py` with unregistered app warning.
- `makemigrations --check` is clean (no missing migrations).
- Existing code in these apps is now accessible via Django ORM and management commands.
