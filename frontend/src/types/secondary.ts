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
export interface StageHeartbeat {
  stage: string;
  symbol_scope: string;
  last_event_at: string;
}
export interface PipelineHealthSnapshot {
  evaluated_at: string;
  overall_status: string;
  stage_statuses: Record<string, string>;
}
export interface PipelineHealth {
  snapshot?: PipelineHealthSnapshot | null;
  heartbeats?: StageHeartbeat[];
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
  rule_execution_id?: string | null;
  analysis_event_id?: string | null;
  strategy_id?: string | null;
  direction?: string;
  side?: string;
  confidence_score?: string;
  severity?: string | null;
  status?: "PUBLISHED" | "ACCEPTED" | "REJECTED" | "EXPIRED" | "DRAFT" | string;
  published_at?: string | null;
  created_at?: string | null;
  explanation?: string | null;
  [key: string]: unknown;
}

// ---- Signals ----
export interface SignalEntry {
  id: string;
  account_id?: string;
  instrument_symbol?: string;
  symbol?: string;
  timeframe?: string;
  rule_id?: string;
  direction?: string;
  side?: string;
  confidence_hint?: string | number | null;
  indicator_snapshot?: unknown;
  source_alert_id?: string | null;
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
  analysis_event_id?: string;
  rule_id?: string;
  symbol?: string;
  event_type?: string;
  status?: string;
  decision?: string;
  rejection_code?: string | null;
  position_size?: number;
  risk_amount?: string | null;
  risk_pct_of_capital?: string | null;
  risk_reward_ratio?: string | null;
  portfolio_gateway_impl?: string;
  reason_message?: string;
  reason?: string | null;
  severity?: string | null;
  trigger_data?: unknown;
  created_at?: string | null;
  [key: string]: unknown;
}

export interface KillSwitchState {
  scope?: string;
  is_active: boolean;
  activated_at?: string | null;
  deactivated_at?: string | null;
  activated_by?: string | null;
  actor?: string | null;
  reason?: string | null;
  [key: string]: unknown;
}

// ---- Portfolio Reconciliation ----
export interface DriftSummary {
  total_drift_count?: number;
  total_drift_value?: string | null;
  drift_by_symbol?: Record<string, unknown>;
  last_reconciled_at?: string | null;
  classification_breakdown?: Record<string, number>;
  total_records?: number;
  last_run_at?: string | null;
  [key: string]: unknown;
}

export type DriftClassification = string; // e.g. 'missing' | 'qty_drift' | 'price_drift' | 'extra'

export interface DriftEntry {
  id: string;
  account_id?: string;
  entity_type?: string;
  entity_key?: string;
  classification?: DriftClassification;
  auto_repaired?: boolean;
  detected_at?: string | null;
  repaired_at?: string | null;
  expected_snapshot?: Record<string, unknown> | null;
  actual_snapshot?: Record<string, unknown> | null;
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
