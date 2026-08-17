// Defensive interfaces for ⚠ endpoints whose exact JSON bodies are NOT VERIFIED.
// Per 08_GAPS_BLACKLIST_AND_ASSUMPTIONS.md: render documented fields; ignore unknowns;
// show `--` for missing. Every interface here uses [key: string]: unknown for forward-compat.

// ---- Journal — VERIFIED against backend (2026-08-17) ----
export interface JournalOrderEvent {
  event_type: string;
  event_id: string;
  occurred_at: string;
  payload: Record<string, unknown>;
  [key: string]: unknown;
}

export interface JournalEntry {
  correlation_id: string;
  account_id: string;
  signal_snapshot: {
    symbol?: string;
    signal_type?: string;
    confidence?: number;
    account_id?: string;
    [key: string]: unknown;
  } | null;
  decision_snapshot: {
    symbol?: string;
    decision?: string;
    quantity?: number;
    account_id?: string;
    [key: string]: unknown;
  } | null;
  order_events: JournalOrderEvent[] | null;
  position_id: string | null;
  outcome: "won" | "lost" | "breakeven" | null;
  realized_pnl: string | null;
  finalized: boolean;
  finalized_at: string | null;
  // ⚠ Snapshot dataclass has no created/updated timestamps — API always returns null.
  created_at: string | null;
  updated_at: string | null;
  [key: string]: unknown;
}

// ---- Audit Log — VERIFIED against backend (2026-08-17) ----
export interface AuditEntry {
  id: string;
  actor: string; // "system" | "user" | "ai"
  action: string;
  target_type: string;
  target_id: string;
  metadata: Record<string, unknown>;
  occurred_at: string;
  created_at: string;
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
  cash?: string;
  margin_used?: string;
  equity?: string;
  available_capital?: string;
  realized_pnl_today?: string;
  unrealized_pnl_today?: string;
  [key: string]: unknown;
}

export interface PortfolioPosition {
  account_id?: string;
  symbol: string;
  side?: string;
  quantity?: string;
  avg_entry_price?: string | null;
  opened_at?: string | null;
  current_price?: string | null;
  unrealized_pnl?: string | null;
  exposure?: string | null;
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

// ---- Analytics & Risk (per-account) — VERIFIED against backend ----
export interface AnalyticsPnl {
  account_id?: string;
  current_total_pnl?: string;
  current_unrealized_pnl?: string;
  peak_cumulative_pnl?: string;
  current_drawdown_pct?: string;
  time_series?: Array<Record<string, unknown>>;
  metadata?: { period?: string; point_count?: number; [k: string]: unknown };
  [key: string]: unknown;
}

export interface AnalyticsDailyRollup {
  trading_date: string;
  realized_pnl: string;
  total_pnl: string;
  cumulative_pnl: string;
  [key: string]: unknown;
}

export interface AnalyticsPerformance {
  account_id?: string;
  period?: string;
  win_rate?: string;
  avg_win?: string;
  avg_loss?: string;
  profit_factor?: string | null;
  expectancy?: string;
  sharpe_like_ratio?: string | null;
  total_trades?: number;
  winning_trades?: number;
  losing_trades?: number;
  [key: string]: unknown;
}

export interface AnalyticsRiskSummary {
  account_id?: string;
  total_exposure?: string;
  largest_position_pct?: string;
  sector_concentration_pct?: string;
  leverage_ratio?: string;
  active_alerts?: Array<Record<string, unknown>>;
  [key: string]: unknown;
}
