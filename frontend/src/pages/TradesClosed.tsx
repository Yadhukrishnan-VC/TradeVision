// TradesClosed — GET /dashboard/trades/closed/.

import { useFetch } from "@/hooks/useFetch";
import { getClosedTrades } from "@/api/dashboard";
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
  { key: "avg_fill_price", header: "Exit", numeric: true, cell: (r) => fmtInr(r.avg_fill_price), sortAccessor: (r) => toNum(r.avg_fill_price) },
  { key: "net_pnl", header: "Net PnL", numeric: true, cell: (r) => <span className={pnlColor(r.net_pnl)}>{fmtInr(r.net_pnl)}</span>, sortAccessor: (r) => toNum(r.net_pnl) },
  { key: "transaction_cost", header: "Tx cost", numeric: true, cell: (r) => fmtInr(r.transaction_cost), sortAccessor: (r) => toNum(r.transaction_cost) },
  { key: "closed_at", header: "Closed", cell: (r) => fmtDateTime(r.closed_at), sortAccessor: (r) => r.closed_at || "" },
];

export function TradesClosed() {
  const { data, state, error, refetch } = useFetch(getClosedTrades);
  return (
    <div className="space-y-4">
      <div>
        <h1 className="text-2xl font-bold text-slate-900">Closed Trades</h1>
        <p className="text-sm text-slate-500 mt-1">GET /dashboard/trades/closed/</p>
      </div>
      {state === "error" && error && (
        <Alert tone="error" code={error.code} onRetry={refetch}>{error.message}</Alert>
      )}
      <Card>
        {state === "loading" ? (
          <DataTable columns={columns} rows={[]} loading rowKey={(_, i) => String(i)} />
        ) : state === "empty" || !data || data.results.length === 0 ? (
          <EmptyState title="No closed trades" />
        ) : (
          <DataTable columns={columns} rows={data.results} rowKey={(r, i) => r.trade_id || r.order_id || String(i)} initialSortKey="closed_at" initialSortDir="desc" />
        )}
      </Card>
    </div>
  );
}
