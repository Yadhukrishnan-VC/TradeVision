// TradesOpen — GET /dashboard/trades/open/. Same shape as Trades page.

import { useFetch } from "@/hooks/useFetch";
import { getOpenTrades } from "@/api/dashboard";
import { Card, Alert, EmptyState, Chip } from "@/components";
import { DataTable, type Column } from "@/components/DataTable";
import { fmtInr, fmtDecimal, toNum, pnlColor } from "@/lib/decimal";
import { fmtDateTime } from "@/lib/time";
import type { TradeRecord } from "@/types/dashboard";

const columns: Column<TradeRecord>[] = [
  { key: "symbol", header: "Symbol", cell: (r) => <span className="font-medium">{r.symbol}</span>, sortAccessor: (r) => r.symbol },
  { key: "side", header: "Side", cell: (r) => <Chip tone={r.side === "LONG" || r.side === "BUY" ? "emerald" : "rose"}>{r.side}</Chip> },
  { key: "quantity", header: "Qty", numeric: true, cell: (r) => fmtDecimal(r.quantity || "0", 0), sortAccessor: (r) => toNum(r.quantity) },
  { key: "entry_price", header: "Entry", numeric: true, cell: (r) => fmtInr(r.entry_price), sortAccessor: (r) => toNum(r.entry_price) },
  { key: "unrealized_pnl", header: "Unrealized PnL", numeric: true, cell: (r) => <span className={pnlColor(r.realized_pnl)}>{fmtInr(r.realized_pnl)}</span>, sortAccessor: (r) => toNum(r.realized_pnl) },
  { key: "status", header: "Status", cell: (r) => <Chip tone="amber">{r.status}</Chip>, sortAccessor: (r) => r.status || "" },
  { key: "created_at", header: "Opened", cell: (r) => fmtDateTime(r.created_at), sortAccessor: (r) => r.created_at || "" },
];

export function TradesOpen() {
  const { data, state, error, refetch } = useFetch(getOpenTrades);
  return (
    <div className="space-y-4">
      <div>
        <h1 className="text-2xl font-bold text-slate-900 dark:text-slate-100">Open Trades</h1>
        <p className="text-sm text-slate-500 dark:text-slate-400 mt-1">GET /dashboard/trades/open/</p>
      </div>
      {state === "error" && error && (
        <Alert tone="error" code={error.code} onRetry={refetch}>{error.message}</Alert>
      )}
      <Card>
        {state === "loading" ? (
          <DataTable columns={columns} rows={[]} loading rowKey={(_, i) => String(i)} />
        ) : state === "empty" || !data || data.results.length === 0 ? (
          <EmptyState title="No open trades" />
        ) : (
          <DataTable columns={columns} rows={data.results} rowKey={(r, i) => r.trade_id || r.order_id || String(i)} initialSortKey="created_at" initialSortDir="desc" />
        )}
      </Card>
    </div>
  );
}
