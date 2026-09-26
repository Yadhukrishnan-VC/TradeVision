# Project: TradeVision — Session Memory

## Environment / Commands
- Repo: `/home/yk/Documents/TradeVision`. Backend bind-mounted `/app` (dev compose), DB via `docker exec infra-postgres-1 env PGPASSWORD=tradevision_password psql -U tradevision -d tradevision_dev_db`.
- Backend restart: `cd infra && docker compose -f docker-compose.yml -f docker-compose.dev.yml restart backend` — **kills in-flight `docker exec -d` batch commands**; runs resume from `last_processed_snapshot_id` cursor.
- Frontend typecheck: `docker exec infra-frontend-1 sh -lc "cd /app && node_modules/.bin/tsc -b"` (no node on host; `npx`/`ps`/`pgrep`/`pkill` absent — kill via `/proc` scan).
- Long ops exceed 120s bash cap → `docker exec -d` + poll DB. Backtest batch: `docker exec -d infra-backend-1 sh -lc "python manage.py per_symbol_backtests --symbols <SYM> --days 730"`; default (no `--symbols`) = all watchlist symbols, sequential; single symbol = parallel 6-run (days default 365, batch used 730). Output `/dev/null`.
- Celery env: `config/settings/base.py` sets `CELERY_BEAT_SCHEDULE_CELERYBEAT_ENTRIES` (DatabaseScheduler). Workers: worker-default consumes `notifications,analytics,default,maintenance,monitoring,webhooks` (hostname `worker-default@%h`); worker-market consumes `market_data,processing,intelligence,rule_engine`; worker-ai consumes `ai`. Beat=celery-beat. Restart a worker to load new code + esp. new beat entries: `docker compose ... restart celery-beat celery-worker-default`.
- Dev settings = `config.settings.development`, which does `from .base import *` (base is the source of truth for beat/schedule).

## Objective (current sprint)
Per-stock strategy ranking: backtest each ACTIVE strategy per watchlist symbol, persist `StrategySymbolAffinity` for gate-cleared combos (≥30 trades, expectancy>0, PF>1.3, maxDD<20%), let `StrategyMatcher` prefer top backtested strategy per symbol. Feature committed (`80a6bc2`, `737bf7a`). Evidence batch running in background; ranking only runs per symbol after all its 6 runs complete (it runs at command end automatically, or standalone via `SymbolRankingService().rank_symbols([...])`).
**Automation added this session**: nightly Celery Beat task `tradevision.strategy_registry.run_watchlist_per_symbol_backtests` (03:00 IST, queue `analytics`) shells out to `per_symbol_backtests` as an isolated subprocess (must NOT run via `call_command`/in-process — the command force-sets `CELERY_TASK_ALWAYS_EAGER` + `BACKTEST_NO_REDIS_MIRROR` which would corrupt worker task routing for the duration). New watchlist symbols get backtested+ranked automatically on the next nightly tick. Sync confirmed: DB `django_celery_beat_periodictask` row enabled (crontab_id=5), worker-default has task registered. Not yet committed; infra/docker-compose*.yml + backend/.env.active + infra/frontend/ must stay uncommitted.

## Architecture / Mapping (fixed facts)
- `core/execution_context.py` exports `get_account_override`, `bind_account_override`, `bind_backtest_execution`, `bind_forced_strategy`, `bind_backtest_rules` — NO `bind_simulated_time` (ImportError; runner handles simulated time itself).
- `apps/backtesting/services.py` = module file (not pkg). Replay bridge = `apps/backtesting/replay_signal_execution.py`.
- RuleFired payload: `symbol,event_type,rule_id,severity,trigger_data,analysis_event_id,occurred_at,account_id` (account_id only when override). Correlation = `analysis_event_id`; dedup `risk_approved_event_id=uuid5(_REPLAY_NS,"replay:{event_id}")`.
- Drain replay path: `REPLAY_DRAIN_CHAIN_ONLY` (default True) whitelists TA→"intelligence" only, PacketBuilt→"rule_engine" only; RuleFired during replay → `ReplaySignalExecutionService.handle_rule_fired` → `ExecutionRequestService.intake` (symbol, rule_id, event_type, direction, entry_price, stop_loss, position_size, account_id).
- Bridge pricing: entry from trigger_data (entry_price/price/close/open/breakout_price); stop from stop_loss/stop_price else fallback (`BACKTEST_STOP_FALLBACK_PCT` 0.02); qty = 1% capital (`BACKTEST_RISK_PER_TRADE_PCT`) / |entry−stop|. Side: `short_sell_v1`, `short_breakdown_v1` → SHORT; else LONG.
- `BACKTEST_NO_REDIS_MIRROR` guard in `apps/eventbus/infrastructure/redis_event_bus.py` publish(); command sets it.
- Watchlist: HDFCBANK, ICICIBANK, INFY, ITC, LT, RELIANCE, SBIN, TCS. 8 ACTIVE strategies: Setups 1–4, 6–8 + Breakout (Default), priorities 1–8. Map in `apps/strategy_registry/application/strategy_rule_map.py`, seed in `apps/rule_engine/management/commands/seed_trading_defaults.py`.
- Fire reality (730d/stock): `long_momentum_v1`/`short_sell_v1` rarely fire (Setup 1/2 runs stay at 0 fills — correct); `volatility_breakout_v1`, `breakout_v1`, `price_movement_v1`, `volume_spike_v1` fire often.
- Ambient noise: external Celery workers drain the ~22K `TechnicalAnalysisCompleted` backlog producing isolated executions (no account_id) — NOT run evidence. Do not count.
- Risk layer #3 hard-proof intentionally NOT done: `high_beta_breakout_rule.py`/`short_breakdown_rule.py` refuse to invent stops (fail-closed ADR gate) — do not override. Live (non-replay) order chain remains fail-closed MISSING_STOP_LOSS by design.

## Open items
- Batch: HDFCBANK Volatility Breakout RUNNING ~28 fills (gate MIN_TRADE_COUNT=30); ICICIBANK/INFY/RELIANCE/SBIN on Short Sell RUNNING 0; ITC/LT/TCS Long Momentum RUNNING; TCS Breakout PENDING; several Long Momentum COMPLETED 0. No `StrategySymbolAffinity` rows yet. Follow-up batch still needed to include Setup 7/8 (Price Momentum, Volume Spike) for all symbols after current batch drains.
- Disk: host `/` 98% full. `docker system/volume prune` reclaimed ~80MB only. `erp-core` image 1.1GB unused — awaiting user confirmation before removal. Redis `events:` streams backlog trim not done.
- Nightly beat task not yet committed.
- Live external drain still head-of-line-blocked (out of sprint scope).