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

/** PositionSnapshotSerializer — ⚠ partial field list. */
export interface PositionSnapshot {
  position_id: string;
  account_id: string;
  symbol: string;
  side: "LONG" | "SHORT" | string;
  quantity?: string;
  avg_cost?: string | null;
  market_value?: string | null;
  unrealized_pnl?: string | null;
  opened_at?: string | null;
  [key: string]: unknown;
}

/** OrderSnapshotSerializer — ⚠ partial field list. */
export interface OrderSnapshot {
  order_id: string;
  account_id?: string;
  symbol: string;
  side?: "LONG" | "SHORT" | string;
  quantity?: string;
  entry_price?: string | null;
  avg_fill_price?: string | null;
  filled_quantity?: string;
  status?: string;
  correlation_id?: string | null;
  created_at?: string | null;
  [key: string]: unknown;
}

/** TradeRecordSerializer — ⚠ partial field list. */
export interface TradeRecord {
  trade_id?: string;
  order_id?: string;
  account_id?: string;
  symbol: string;
  side?: string;
  quantity?: string;
  entry_price?: string | null;
  avg_fill_price?: string | null;
  filled_quantity?: string;
  realized_pnl?: string | null;
  net_pnl?: string | null;
  transaction_cost?: string | null;
  status?: string;
  correlation_id?: string | null;
  created_at?: string | null;
  closed_at?: string | null;
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
