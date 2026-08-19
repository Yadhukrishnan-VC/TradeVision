// Orders — GET /dashboard/orders/.

import { useFetch } from "@/hooks/useFetch";
import { getOrders } from "@/api/dashboard";
import { Card, Alert, EmptyState, Chip } from "@/components";
import { DataTable, type Column } from "@/components/DataTable";
import { useNavigate } from "react-router-dom";
import { fmtInr, fmtDecimal, toNum } from "@/lib/decimal";
import { fmtDateTime } from "@/lib/time";
import type { OrderSnapshot } from "@/types/dashboard";

export function Orders() {
  const { data, state, error, refetch } = useFetch(getOrders);
  const navigate = useNavigate();

  const columns: Column<OrderSnapshot>[] = [
    { key: "symbol", header: "Symbol", cell: (r) => <span className="font-medium">{r.symbol}</span>, sortAccessor: (r) => r.symbol },
    { key: "side", header: "Side", cell: (r) => <Chip tone={r.side === "LONG" ? "emerald" : "rose"}>{r.side}</Chip> },
    { key: "quantity", header: "Qty", numeric: true, cell: (r) => fmtDecimal(r.quantity || "0", 0), sortAccessor: (r) => toNum(r.quantity) },
    { key: "entry_price", header: "Entry", numeric: true, cell: (r) => fmtInr(r.entry_price), sortAccessor: (r) => toNum(r.entry_price) },
    { key: "avg_fill_price", header: "Avg fill", numeric: true, cell: (r) => fmtInr(r.avg_fill_price), sortAccessor: (r) => toNum(r.avg_fill_price) },
    { key: "filled_quantity", header: "Filled", numeric: true, cell: (r) => fmtDecimal(r.filled_quantity || "0", 0), sortAccessor: (r) => toNum(r.filled_quantity) },
    { key: "status", header: "Status", cell: (r) => <Chip tone={r.status === "FILLED" ? "emerald" : r.status === "REJECTED" ? "rose" : "amber"}>{r.status}</Chip>, sortAccessor: (r) => r.status || "" },
    { key: "created_at", header: "Created", cell: (r) => fmtDateTime(r.created_at), sortAccessor: (r) => r.created_at || "" },
  ];

  return (
    <div className="space-y-4">
      <div>
        <h1 className="text-2xl font-bold text-slate-900 dark:text-slate-100">Orders</h1>
        <p className="text-sm text-slate-500 dark:text-slate-400 mt-1">GET /dashboard/orders/</p>
      </div>
      {state === "error" && error && (
        <Alert tone="error" code={error.code} onRetry={refetch}>{error.message}</Alert>
      )}
      <Card>
        {state === "loading" ? (
          <DataTable columns={columns} rows={[]} loading rowKey={(_, i) => String(i)} />
        ) : state === "empty" || !data || data.results.length === 0 ? (
          <EmptyState title="No orders" description="There are no orders on this account." />
        ) : (
          <DataTable
            columns={columns}
            rows={data.results}
            rowKey={(r) => r.order_id}
            onRowClick={(r) => navigate(`/orders/${r.order_id}`)}
            initialSortKey="created_at"
            initialSortDir="desc"
            emptyTitle="No orders"
          />
        )}
      </Card>
      {data && data.count > data.results.length && (
        <p className="text-xs text-slate-500 dark:text-slate-400">Showing {data.results.length} of {data.count}.</p>
      )}
    </div>
  );
}
