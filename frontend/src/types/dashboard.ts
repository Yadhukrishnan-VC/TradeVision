// Trading Core dashboard types.
// SOURCE: 04_API_CONTRACT.md — serializers for /api/v1/dashboard/*.

/**
 * DashboardHomeSummarySerializer — VERIFIED field list.
 * Numeric fields arrive as STRINGS (str(Decimal)).
 */
export interface DashboardHomeSummary {
  account_id: string;
  open_positions_count: number;
  open_orders_count: number;
  today_realized_pnl: string;
  today_unrealized_pnl: string;
  active_alerts_count: number;
  broker_connection_status: string | null;
  market_session_status: string | null;
  last_updated_at: string | null;
  // Defensive: render unknown extras as ignored.
  [key: string]: unknown;
}

/** Portfolio composition top-level (verified fields). */
export interface PortfolioComposition {
  account_id: string;
  total_market_value: string;
  total_cost_basis: string;
  cash_balance: string;
  holdings?: Holding[];
  [key: string]: unknown;
}

/** HoldingSerializer — verified field set. */
export interface Holding {
  account_id: string;
  symbol: string;
  quantity: string;
  avg_cost: string;
  cost_basis: string;
  market_value: string | null;
  allocation_pct: string | null;
  unrealized_pnl: string | null;
  opened_at: string | null;
  [key: string]: unknown;
}

/** PositionSnapshotSerializer — field list verified against backend. */
export interface PositionSnapshot {
  position_id: string;
  account_id: string;
  symbol: string;
  side: "LONG" | "SHORT" | string;
  quantity?: string;
  entry_price?: string | null;
  current_price?: string | null;
  unrealized_pnl?: string | null;
  unrealized_pnl_pct?: string | null;
  is_open?: boolean;
  opened_at?: string | null;
  closed_at?: string | null;
  avg_cost?: string | null;
  market_value?: string | null;
  [key: string]: unknown;
}

/** OrderSnapshotSerializer — field list verified against backend. */
export interface OrderSnapshot {
  order_id: string;
  account_id?: string;
  symbol: string;
  side?: "LONG" | "SHORT" | string;
  quantity?: string;
  order_type?: string;
  status?: string;
  filled_quantity?: string;
  avg_fill_price?: string | null;
  limit_price?: string | null;
  placed_at?: string | null;
  entry_price?: string | null;
  created_at?: string | null;
  correlation_id?: string | null;
  [key: string]: unknown;
}

/** TradeRecordSerializer — field list verified against backend. */
export interface TradeRecord {
  trade_id?: string;
  order_id?: string;
  account_id?: string;
  symbol: string;
  side?: string;
  quantity?: string;
  entry_price?: string | null;
  exit_price?: string | null;
  realized_pnl?: string | null;
  realized_pnl_pct?: string | null;
  opened_at?: string | null;
  closed_at?: string | null;
  holding_period_seconds?: number;
  avg_fill_price?: string | null;
  filled_quantity?: string;
  status?: string;
  net_pnl?: string | null;
  transaction_cost?: string | null;
  unrealized_pnl?: string | null;
  created_at?: string | null;
  [key: string]: unknown;
}

/** ExportRequestSerializer / ExportJobSerializer — verified against backend. */
export interface ExportJob {
  export_id: string;
  status?: string;
  format?: string;
  requested_at?: string | null;
  completed_at?: string | null;
  /** Download URL — only rendered IF present in the response. */
  file_url?: string | null;
  error_message?: string | null;
  [key: string]: unknown;
}
