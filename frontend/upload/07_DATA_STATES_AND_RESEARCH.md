# 07 — Data States, Errors, and Research Features

## API error envelope (VERIFIED)

All domain errors are returned as:
```json
{"error": {"code": "<snake_case_code>", "message": "<human message>", "details": {...optional}}}
```
- 400 validation_error / domain_error; 403 permission_denied; 404 not_found; 409 concurrency_error.
- SOURCE: `backend/apps/common/infrastructure/drf_exception_handler.py:48`
- DRF framework errors (e.g. serializer field validation via `raise_exception=True`) return DRF's standard error body (`{"field": ["message"], "detail": "..."}`), NOT the envelope above. Both shapes must be handled.
- Login/refresh return a custom shape: `{"error": {"code": "invalid_credentials"|"account_disabled"|"invalid_refresh_token", "message": "..."}}` (401). SOURCE: `backend/apps/accounts/interfaces/api/views.py:43,102`

## Pagination envelope (VERIFIED)

List endpoints: `{"count": N, "next": "<url>|null", "previous": "<url>|null", "results": [...]}`.
SOURCE: `backend/config/settings/base.py:197`

## Frontend data-state model (implement for every fetch)

1. **idle** — nothing requested yet.
2. **loading** — request in flight; show skeleton rows/cards (per 02).
3. **success** — payload present; render. If the payload is `{}` / empty `results` / all-`null` → render **EmptyState**, not a blank area.
4. **error** — non-2xx:
   - If body matches `{"error": {code, message}}` → show Alert with `message`; use `code` for an optional icon/known-code map.
   - If body is DRF-style field errors → show field-level messages.
   - If network failure → "Cannot reach server" Alert with retry.
5. **stale/partial** — for long-running jobs (backtest runs, export) poll while showing a progress banner; if a field inside a successful payload is `null`, render `--` for that cell only.

## Nullability rules (VERIFIED fields that can be null)

- `profit_factor`, `sharpe_ratio`, `sortino_ratio`, `benchmark_return_pct` → `null` when not computable (empty bucket / no data). Render `--`.
- `stats.available_capital`/`equity_at_completion` → `"0"` when no capital state.
- Walk-forward `distribution.*.min/max/median` → `null` when no included windows (show `--`, plus `count: 0`).
- `has_edge` → `true|false|null` (null = insufficient data — the UI must show a distinct "insufficient data" badge, never treat null as False).
- `breakeven_commission_rate` / `breakeven_slippage_bps` → `null` for NEVER_PROFITABLE.
- `started_at` / `completed_at` → `null` while a run is PENDING.
- `TASnapshot`-backed fields, `Instrument.expiry`, position `opened_at`, `market_value`/`allocation_pct`/`unrealized_pnl` → nullable per 05.

## Never

- Convert a `null`/missing value into `0` or a fabricated trend.
- Show a hardcoded demo dataset anywhere.
- Fail the page because one optional field is null — degrade per-field.
- Retry POSTs automatically (backtests/analysis jobs are expensive and create accounts). Always require a user-triggered retry.

## Research Features (Backtesting Domain)

The research engine is the core of TradeVision. This ties the mechanics to the UI.

### Lifecycle of a backtest run

1. `POST /backtesting/runs/` → creates isolated `Account` (named "Backtest <SYMBOL> <date>", `is_default=False`), deposits `initial_capital` (default ₹1,000,000) via `CapitalService`, creates `BacktestRun` status=PENDING, enqueues Celery `run_backtest`.
   SOURCE: `backend/apps/backtesting/interfaces/api/views.py:39`
2. Worker replays TASnapshot candles for `[range_start, range_end]`, runs the rule engine in simulated time (contextvars + `bind_account_override`), fills orders via PaperBroker at `commission_rate` and `slippage_bps`.
   SOURCE: `backend/apps/backtesting/services.py` (BacktestRunnerService)
3. On completion, `BacktestStatsService.run_stats(run)` computes everything and persists aggregates onto the run.
   SOURCE: `backend/apps/backtesting/services.py:222`
4. `GET /backtesting/runs/:id/` returns `{...run fields, "stats": <run_stats>}`.
   SOURCE: `backend/apps/backtesting/interfaces/api/views.py:83`

### What `run_stats` contains (the dashboard's "research result")

Full verified shape in `04_API_CONTRACT.md`. Highlights:
- Top-level: trade/fill/win/loss counts, gross P/L, net PnL, win rate, expectancy, profit factor, max drawdown %, Sharpe, Sortino, benchmark return %, equity at completion, available capital, risk-rejected count, total transaction costs, total slippage impact.
- `in_sample` / `out_of_sample`: the SAME metric set computed on each half of the static `in_sample_ratio` date split (split once by timestamp).
- `by_regime`: per-regime buckets (regime read from each order's `correlation_id` → RuleExecution.`trigger_data["regime"]`).
- `by_rule`: per-rule buckets (attribution via correlation_id → RuleExecution.analysis_event_id), plus `unattributed_trade_count`.
- `trades[]`: per-order records (order_id, side, quantity, entry/avg fill price, realized/net PnL, transaction cost, created_at).
SOURCE: `backend/apps/backtesting/services.py:653`

### Walk-forward

Sliding `window_size_days` windows stepped by `step_size_days`; each window = its own isolated run+account; per-window IS/OOS metrics; OOS distribution (min/max/median/count_positive) over windows with ≥ `MIN_TRADES_FOR_DISTRIBUTION=2` OOS trades.
SOURCE: `backend/apps/backtesting/application/walk_forward_service.py:31,108,191`

### Edge validation

Runs the full evaluation at zero cost and at the caller's realistic cost (`realistic_commission_rate` default 0.0003, `realistic_slippage_bps` default 5.0). Per rule: `has_edge` at both levels, `flipped` if the verdict changed (only True/False → True/False flips; a `null` insufficiency never flips). Edge criterion is an internal constant (`EDGE_CRITERION`) — do not replicate its formula; display it as returned.
SOURCE: `backend/apps/backtesting/application/edge_validation_service.py:198,290`

### Cost sensitivity

Sweeps a commission×slippage grid (max `MAX_GRID_POINTS=50`); per rule, computes breakeven commission/slippage and classifies:
- `BREAKEVEN_FOUND` — expectancy crosses zero at a tested level (breakeven values provided).
- `NEVER_PROFITABLE` — negative at every tested level (breakeven `null`; never fabricate a zero or extrapolation).
- `SURVIVES_FULL_RANGE` — positive through the tested range (breakeven = tested max as an honest survivability floor).
Each point's `series[]` = `{cost_level, expectancy}` is plot-ready.
SOURCE: `backend/apps/backtesting/application/cost_sensitivity_service.py:46,267,336`

### Rule firing validation gate (ADR-029)

`RuleValidationService` evaluates each rule's empirical edge per market regime and persists `{"<regime>": "GO"|"NO_GO"|"INSUFFICIENT_DATA"}` into `RuleConfig.validated_regimes` (creating the RuleConfig `enabled=False` when absent). The firing gate (`_filter_by_gate`) suppresses rule fires unless the current regime's status == `"GO"`. Replay-aware: gate is bypassed during backtest replay via `get_account_override()` (so historical backtests are not filtered).
SOURCE: `backend/apps/backtesting/application/rule_validation_service.py`, `backend/apps/rule_engine/infrastructure/models.py:20`, ADR-029

### UI implications

- Every research action is a synchronous, potentially slow POST for walk-forward/edge/cost — show a prominent "computing…" state and never auto-retry.
- Backtest creation returns immediately (async); poll run detail for PENDING → RUNNING → COMPLETED/FAILED.
- Show `failure_reason` on FAILED runs.
- Surface ADR-029 gate status in the Rules UI (GO/NO_GO/INSUFFICIENT_DATA chips per rule+regime).
- Numbers are strings (Decimal); format for display only.