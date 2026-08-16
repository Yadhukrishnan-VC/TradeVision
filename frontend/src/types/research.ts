// Research / Backtesting types.
// SOURCE: 04_API_CONTRACT.md — every shape VERIFIED.
// All Decimal values arrive as strings; null when not computable.

/** POST /backtesting/runs/ request (BacktestRunCreateSerializer). */
export interface BacktestRunCreateRequest {
  symbol: string;
  timeframe?: string; // default ""
  range_start: string; // ISO-8601
  range_end: string;
  initial_capital?: string; // default "1000000"
}

/** POST /backtesting/runs/ 201 response (VERIFIED, views.py:69). */
export interface BacktestRunCreated {
  run_id: string;
  account_id: string;
  status: "PENDING";
  symbol: string;
  timeframe: string;
  range_start: string;
  range_end: string;
}

export type BacktestRunStatus =
  | "PENDING"
  | "RUNNING"
  | "COMPLETED"
  | "FAILED"
  | string;

/** Metrics bucket — used for in_sample, out_of_sample, by_regime[*], by_rule[*]. */
export interface MetricsBucket {
  trade_count: number;
  win_count: number;
  loss_count: number;
  gross_profit: string;
  gross_loss: string;
  total_transaction_costs: string;
  net_pnl: string;
  win_rate: string;
  avg_win: string;
  avg_loss: string;
  expectancy: string;
  profit_factor: string | null;
  sharpe_ratio: string | null;
  sortino_ratio: string | null;
  max_drawdown_pct: string;
  max_drawdown_amount: string;
  // Per 06_CHARTS.md NOTE: buckets DO contain equity_curve and returns arrays.
  equity_curve?: string[];
  returns?: string[];
  trades?: BacktestTrade[];
  [key: string]: unknown;
}

/** Per-rule bucket extends MetricsBucket with rule_id (verified shape). */
export interface RuleBucket extends MetricsBucket {
  rule_id: string;
}

/** Per-trade record inside run_stats.trades[] (verified). */
export interface BacktestTrade {
  order_id: string;
  symbol: string;
  side: string;
  quantity: string;
  entry_price: string;
  avg_fill_price: string;
  filled_quantity: string;
  status: string;
  realized_pnl: string;
  net_pnl: string;
  transaction_cost: string;
  created_at: string;
  [key: string]: unknown;
}

/** run_stats payload — VERIFIED full shape (services.py:653). */
export interface RunStats {
  status: BacktestRunStatus;
  trade_count: number;
  fill_count: number;
  win_count: number;
  loss_count: number;
  risk_rejected_count: number;
  gross_profit: string;
  gross_loss: string;
  total_transaction_costs: string;
  total_slippage_impact: string;
  net_pnl: string;
  win_rate: string;
  expectancy: string;
  profit_factor: string | null;
  max_drawdown_pct: string;
  sharpe_ratio: string | null;
  sortino_ratio: string | null;
  benchmark_return_pct: string | null;
  equity_at_completion: string;
  available_capital: string;
  in_sample: MetricsBucket;
  out_of_sample: MetricsBucket;
  by_regime: Record<string, MetricsBucket>;
  missing_regime_count: number;
  by_rule: Record<string, RuleBucket>;
  unattributed_trade_count: number;
  trades: BacktestTrade[];
  // NOTE: a top-level `equity_curve` key is NOT in the verified shape — do not
  // assume it exists (gap P3). Build merged equity curve from trades[].net_pnl
  // cumulative, or use in_sample/out_of_sample.equity_curve arrays.
  [key: string]: unknown;
}

/** GET /backtesting/runs/:id/ response (verified). */
export interface BacktestRunDetail {
  run_id: string;
  status: BacktestRunStatus;
  account_id: string;
  symbol: string;
  timeframe: string;
  range_start: string;
  range_end: string;
  failure_reason: string;
  started_at: string | null;
  completed_at: string | null;
  stats: RunStats | null; // null while PENDING/RUNNING
  [key: string]: unknown;
}

/** POST /backtesting/walk-forward/ request (verified). */
export interface WalkForwardRequest {
  symbol: string;
  timeframe?: string;
  range_start: string;
  range_end: string;
  window_size_days: number; // >=1
  step_size_days: number; // >=1
  in_sample_ratio?: string; // default "0.70"
  initial_capital?: string;
}

export interface WalkForwardWindow {
  window_index: number;
  range_start: string;
  range_end: string;
  run_id: string;
  account_id: string;
  status: BacktestRunStatus;
  in_sample_trade_count: number;
  out_of_sample_trade_count: number;
  in_sample_expectancy: string;
  out_of_sample_expectancy: string;
  out_of_sample_sharpe_ratio: string | null;
  out_of_sample_win_rate: string;
  [key: string]: unknown;
}

export interface WalkForwardDistributionEntry {
  count: number;
  min: string | null;
  max: string | null;
  median: string | null;
  count_positive: number;
}

export interface WalkForwardDistribution {
  out_of_sample_expectancy: WalkForwardDistributionEntry;
  out_of_sample_sharpe_ratio: WalkForwardDistributionEntry;
  out_of_sample_win_rate: WalkForwardDistributionEntry;
}

/** POST /backtesting/walk-forward/ 200 response (VERIFIED, walk_forward_service.py:191). */
export interface WalkForwardResponse {
  symbol: string;
  timeframe: string;
  range_start: string;
  range_end: string;
  window_size_days: number;
  step_size_days: number;
  in_sample_ratio: string;
  total_windows: number;
  included_window_count: number;
  excluded_window_count: number;
  windows: WalkForwardWindow[];
  distribution: WalkForwardDistribution;
}

/** POST /backtesting/edge-validation/ request (verified). */
export interface EdgeValidationRequest {
  symbol: string;
  timeframe?: string;
  range_start: string;
  range_end: string;
  window_size_days: number;
  step_size_days: number;
  in_sample_ratio?: string; // default "0.70"
  realistic_commission_rate?: string; // default "0.0003"
  realistic_slippage_bps?: string; // default "5.0"
  initial_capital?: string;
}

/** Edge criterion — VERIFIED literal dict (edge_validation_service.py:64). */
export interface EdgeCriterion {
  expectancy_greater_than_zero: boolean;
  profit_factor_not_none: boolean;
  profit_factor_greater_than_one: string;
  min_trades: number;
  insufficient_data: string;
}

/** Single-rule report inside edge validation. */
export interface EdgeRuleReport {
  rule_id: string;
  trade_count: number;
  win_rate: string;
  expectancy: string;
  profit_factor: string | null;
  sharpe_ratio: string | null;
  sortino_ratio: string | null;
  max_drawdown_pct: string;
  /** true | false | null (null = insufficient data — never False). */
  has_edge: boolean | null;
}

/** Embedded evaluate report (edge_validation_service.py:182). */
export interface EdgeEvaluateReport {
  symbol: string;
  timeframe: string;
  range_start: string;
  range_end: string;
  window_size_days: number;
  step_size_days: number;
  in_sample_ratio: string;
  commission_rate: string;
  slippage_bps: string;
  edge_criterion: EdgeCriterion;
  single_run?: unknown;
  walk_forward?: unknown;
  by_rule?: Record<string, EdgeRuleReport>;
  [key: string]: unknown;
}

/** Per-rule edge entry. */
export interface EdgeByRuleEntry {
  rule_id: string;
  baseline_has_edge: boolean | null;
  realistic_cost_has_edge: boolean | null;
  /** True only if a True↔False flip occurred; null insufficiency never flips. */
  flipped: boolean;
  baseline: EdgeEvaluateReport;
  realistic_cost: EdgeEvaluateReport;
}

/** POST /backtesting/edge-validation/ 200 response (VERIFIED, edge_validation_service.py:290). */
export interface EdgeValidationResponse {
  symbol: string;
  timeframe: string;
  range_start: string;
  range_end: string;
  window_size_days: number;
  step_size_days: number;
  in_sample_ratio: string;
  realistic_commission_rate: string;
  realistic_slippage_bps: string;
  edge_criterion: EdgeCriterion;
  baseline: EdgeEvaluateReport;
  realistic_cost: EdgeEvaluateReport;
  by_rule: Record<string, EdgeByRuleEntry>;
}

/** POST /backtesting/cost-sensitivity/ request (verified). */
export interface CostSensitivityRequest {
  symbol: string;
  timeframe?: string;
  range_start: string;
  range_end: string;
  commission_start: string;
  commission_end: string;
  commission_step: string;
  slippage_start: string;
  slippage_end: string;
  slippage_step: string;
  initial_capital?: string;
}

export type CostSensitivityClassification =
  | "BREAKEVEN_FOUND"
  | "NEVER_PROFITABLE"
  | "SURVIVES_FULL_RANGE"
  | string;

export interface CostSensitivitySeriesPoint {
  cost_level: string;
  expectancy: string;
}

export interface CostSensitivityByRule {
  rule_id: string;
  expectancy_at_min_cost: string;
  expectancy_at_max_cost: string;
  /** null when classification is NEVER_PROFITABLE. */
  breakeven_commission_rate: string | null;
  breakeven_slippage_bps: string | null;
  classification: CostSensitivityClassification;
  series: CostSensitivitySeriesPoint[];
}

/** POST /backtesting/cost-sensitivity/ 200 response (VERIFIED, cost_sensitivity_service.py:267+336). */
export interface CostSensitivityResponse {
  grid_points_run: number;
  by_rule: Record<string, CostSensitivityByRule>;
}
