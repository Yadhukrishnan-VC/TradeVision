// Positions — GET /dashboard/positions/live/.
// Paginated list of PositionSnapshotSerializer.

import { useFetch } from "@/hooks/useFetch";
import { getLivePositions } from "@/api/dashboard";
import { Card, Alert, EmptyState, Chip } from "@/components";
import { DataTable, type Column } from "@/components/DataTable";
import { useNavigate } from "react-router-dom";
import { fmtInr, fmtDecimal, toNum } from "@/lib/decimal";
import { fmtDateTime } from "@/lib/time";
import type { PositionSnapshot } from "@/types/dashboard";

export function Positions() {
  const { data, state, error, refetch } = useFetch(getLivePositions);
  const navigate = useNavigate();

  const columns: Column<PositionSnapshot>[] = [
    { key: "symbol", header: "Symbol", cell: (r) => <span className="font-medium">{r.symbol}</span>, sortAccessor: (r) => r.symbol },
    { key: "side", header: "Side", cell: (r) => <Chip tone={r.side === "LONG" ? "emerald" : "rose"}>{r.side}</Chip> },
    { key: "quantity", header: "Qty", numeric: true, cell: (r) => fmtDecimal(r.quantity || "0", 0), sortAccessor: (r) => toNum(r.quantity) },
    { key: "avg_cost", header: "Avg cost", numeric: true, cell: (r) => fmtInr(r.avg_cost), sortAccessor: (r) => toNum(r.avg_cost) },
    { key: "market_value", header: "Market value", numeric: true, cell: (r) => fmtInr(r.market_value), sortAccessor: (r) => toNum(r.market_value) },
    { key: "unrealized_pnl", header: "Unrealized PnL", numeric: true, cell: (r) => <span className={toNum(r.unrealized_pnl)! > 0 ? "text-emerald-600" : toNum(r.unrealized_pnl)! < 0 ? "text-rose-600" : "text-slate-500"}>{fmtInr(r.unrealized_pnl)}</span>, sortAccessor: (r) => toNum(r.unrealized_pnl) },
    { key: "opened_at", header: "Opened", cell: (r) => fmtDateTime(r.opened_at), sortAccessor: (r) => r.opened_at || "" },
  ];

  return (
    <div className="space-y-4">
      <div>
        <h1 className="text-2xl font-bold text-slate-900">Live Positions</h1>
        <p className="text-sm text-slate-500 mt-1">GET /dashboard/positions/live/</p>
      </div>

      {state === "error" && error && (
        <Alert tone="error" code={error.code} onRetry={refetch}>{error.message}</Alert>
      )}

      <Card>
        {state === "loading" ? (
          <DataTable columns={columns} rows={[]} loading rowKey={(_, i) => String(i)} />
        ) : state === "empty" || !data || data.results.length === 0 ? (
          <EmptyState title="No live positions" description="There are no open positions on this account." />
        ) : (
          <DataTable
            columns={columns}
            rows={data.results}
            rowKey={(r) => r.position_id}
            onRowClick={(r) => navigate(`/positions/${r.position_id}`)}
            initialSortKey="symbol"
            emptyTitle="No live positions"
          />
        )}
      </Card>
      {data && data.count > data.results.length && (
        <p className="text-xs text-slate-500">Showing {data.results.length} of {data.count}. Use pagination endpoint to load more.</p>
      )}
    </div>
  );
}
