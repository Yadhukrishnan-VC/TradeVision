# TradeVision Architecture

## Deterministic Risk Management (ADR-027)

The pre-trade gate is a fixed, fail-closed chain of deterministic checks in
`apps/risk_management/domain/rules/`, evaluated by `RiskEvaluationService` in
this order — first rejection wins; any unexpected error rejects with
`RejectionReason.UNKNOWN`:

1. `KillSwitchCheck`
2. `DataFreshnessCheck`
3. `MarketSessionCheck`
4. `InstrumentCheck`
5. `StopDirectionCheck`
6. `PositionSizingCheck`
7. `ExposureLimitCheck`
8. `DailyLossLimitCheck`
9. `RiskRewardCheck`

### Configuration

All thresholds live in the `RISK_MANAGEMENT` dict in
`config/settings/base.py`, env-overridable (`RISK_MAX_POSITION_SIZE`,
`RISK_MAX_EXPOSURE_CAP`, `RISK_DAILY_LOSS_LIMIT`, `RISK_AVAILABLE_CAPITAL`).
Gate checks (`execution.E002`–`E007`) enforce the hard caps at startup; the
warning `execution.W001` compares the configured available capital against the
evidence-based `min_capital = risk_per_unit / risk_pct` per watchlist symbol
(see `apps/backtesting/application/capital_requirement_service.py`), so any
symbol whose stop distance can never clear `PositionSizingCheck` is flagged at
startup — a warning, not a block.

### RiskRewardCheck (`risk_reward_v1`) — cost blind by design

`RiskRewardCheck` passes when

    R:R = |target_price - entry_price| / |entry_price - stop_loss|

meets the configured floor `RISK_MANAGEMENT["min_risk_reward"]` (default `1.0`).

Caveat: the R:R floor is **cost-blind**. Both legs of the ratio are gross —
the numerator ignores brokerage, STT, exchange transaction charges, stamp duty,
slippage and impact cost, and the denominator ignores the same costs on the
exiting side. A trade that clears a `1.0` floor on gross prices can be net
unprofitable after round-trip costs, especially on low risk_per_unit setups
where a flat per-order cost is a larger fraction of both legs. The historical
backtest P&L is cost-realistic (`BACKTEST_COST_MODEL` / `BACKTEST_NSE_COST_MODEL`,
`docs/EDGE_VALIDATION_REPORT_V2.md`), but the live pre-trade R:R floor is not
cost-adjusted. Optional hardening: extend `RiskRewardCheck` to accept a
round-trip cost (bps + flat per order) and evaluate the net R:R against the
floor; until then treat `min_risk_reward` as a gross-minimumum that should be
set conservatively (e.g. `1.5`+) for cost-typical NSE delivery trading.