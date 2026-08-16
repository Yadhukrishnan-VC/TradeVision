// Defensive interfaces for ⚠ endpoints whose exact JSON bodies are NOT VERIFIED.
// Per 08_GAPS_BLACKLIST_AND_ASSUMPTIONS.md: render documented fields; ignore unknowns;
// show `--` for missing. Every interface here uses [key: string]: unknown for forward-compat.

// ---- Journal ----
export interface JournalEntry {
  correlation_id: string;
  entry_type?: string;
  symbol?: string;
  rule_id?: string;
  severity?: string | null;
  payload?: Record<string, unknown>;
  notes?: string | null;
  created_at?: string | null;
  [key: string]: unknown;
}

// ---- Audit Log ----
export interface AuditEntry {
  id: string;
  actor?: string | null;
  action?: string;
  target_type?: string | null;
  target_id?: string | null;
  timestamp?: string | null;
  details?: Record<string, unknown>;
  [key: string]: unknown;
}

// ---- Pipeline Health ----
export interface PipelineHealth {
  status?: string;
  last_run_at?: string | null;
  staleness_seconds?: number | null;
  components?: Record<string, unknown>;
  [key: string]: unknown;
}

// ---- Recommendations ----
export interface Recommendation {
  id: string;
  symbol?: string;
  rule_id?: string;
  side?: string;
  severity?: string | null;
  status?: "PENDING" | "ACCEPTED" | "REJECTED" | string;
  created_at?: string | null;
  explanation?: string | null;
  [key: string]: unknown;
}

// ---- Signals ----
export interface SignalEntry {
  id: string;
  symbol?: string;
  rule_id?: string;
  side?: string;
  severity?: string | null;
  status?: string;
  created_at?: string | null;
  [key: string]: unknown;
}

// ---- Pattern Engine ----
export interface PatternRun {
  id: string;
  status?: string;
  symbol?: string;
  timeframe?: string;
  range_start?: string | null;
  range_end?: string | null;
  pattern_count?: number;
  created_at?: string | null;
  [key: string]: unknown;
}

export interface HistoricalVector {
  id: string;
  symbol?: string;
  timeframe?: string;
  timestamp?: string | null;
  vector?: Record<string, unknown>;
  [key: string]: unknown;
}

// ---- Watchlist ----
export interface WatchlistItem {
  instrument_token: number;
  symbol?: string;
  exchange?: string;
  tradingsymbol?: string;
  name?: string | null;
  segment?: string | null;
  instrument_type?: string | null;
  order?: number;
  added_at?: string | null;
  [key: string]: unknown;
}

// ---- Portfolio (apps/portfolio) ----
export interface PortfolioSummary {
  account_id?: string;
  equity?: string;
  available_capital?: string;
  cash_balance?: string;
  market_value?: string;
  positions?: PortfolioPosition[];
  [key: string]: unknown;
}

export interface PortfolioPosition {
  symbol: string;
  side?: string;
  quantity?: string;
  avg_cost?: string | null;
  market_value?: string | null;
  unrealized_pnl?: string | null;
  [key: string]: unknown;
}

// ---- Risk Management ----
export interface RiskDecision {
  id: string;
  rule_id?: string;
  symbol?: string;
  decision?: string;
  severity?: string | null;
  reason?: string | null;
  created_at?: string | null;
  [key: string]: unknown;
}

export interface KillSwitchState {
  is_active: boolean;
  activated_at?: string | null;
  deactivated_at?: string | null;
  activated_by?: string | null;
  reason?: string | null;
  [key: string]: unknown;
}

// ---- Portfolio Reconciliation ----
export interface DriftSummary {
  total_drift_count?: number;
  total_drift_value?: string | null;
  drift_by_symbol?: Record<string, unknown>;
  last_reconciled_at?: string | null;
  [key: string]: unknown;
}

export interface DriftEntry {
  id: string;
  symbol?: string;
  expected_quantity?: string | null;
  actual_quantity?: string | null;
  drift_quantity?: string | null;
  drift_value?: string | null;
  detected_at?: string | null;
  [key: string]: unknown;
}

// ---- Trader Memory ----
export interface TraderMemoryEntry {
  id: string;
  strategy_id?: string;
  symbol?: string;
  notes?: string | null;
  created_at?: string | null;
  [key: string]: unknown;
}

export interface TraderMemoryProjection {
  strategy_id: string;
  metrics?: Record<string, unknown>;
  [key: string]: unknown;
}

// ---- Ingestion raw events (secondary page) ----
export interface IngestionRawEvent {
  id: string;
  provider?: string;
  symbol?: string;
  received_at?: string | null;
  raw_payload?: Record<string, unknown>;
  [key: string]: unknown;
}

// ---- Analytics & Risk (per-account) — ⚠ bodies NOT VERIFIED ----
export interface AnalyticsPnl {
  account_id?: string;
  total_realized_pnl?: string;
  total_unrealized_pnl?: string;
  net_pnl?: string;
  by_symbol?: Record<string, unknown>;
  by_day?: Array<{ date: string; pnl: string }>;
  [key: string]: unknown;
}

export interface AnalyticsDailyRollup {
  account_id?: string;
  daily?: Array<{ date: string; pnl: string; cumulative?: string }>;
  [key: string]: unknown;
}

export interface AnalyticsPerformance {
  account_id?: string;
  sharpe_ratio?: string | null;
  sortino_ratio?: string | null;
  max_drawdown_pct?: string | null;
  win_rate?: string | null;
  expectancy?: string | null;
  profit_factor?: string | null;
  benchmark_return_pct?: string | null;
  [key: string]: unknown;
}

export interface AnalyticsRiskSummary {
  account_id?: string;
  var_95?: string | null;
  var_99?: string | null;
  exposure?: string | null;
  leverage?: string | null;
  [key: string]: unknown;
}
