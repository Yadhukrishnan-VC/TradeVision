// Trades (history) — GET /dashboard/trades/history/.
// Includes a "Request export" button that POSTs to /dashboard/trades/history/export/.

import { useState } from "react";
import { useFetch } from "@/hooks/useFetch";
import { getTradeHistory, requestTradeExport } from "@/api/dashboard";
import { Card, Alert, EmptyState, Chip, Button } from "@/components";
import { DataTable, type Column } from "@/components/DataTable";
import { useNavigate } from "react-router-dom";
import { fmtInr, fmtDecimal, toNum, pnlColor } from "@/lib/decimal";
import { fmtDateTime } from "@/lib/time";
import type { TradeRecord } from "@/types/dashboard";
import type { NormalizedApiError } from "@/types/common";

export function Trades() {
  const { data, state, error, refetch } = useFetch(getTradeHistory);
  const navigate = useNavigate();
  const [exporting, setExporting] = useState(false);
  const [exportError, setExportError] = useState<NormalizedApiError | null>(null);

  async function handleExport() {
    setExporting(true);
    setExportError(null);
    try {
      const job = await requestTradeExport();
      if (job?.export_id) {
        navigate(`/trades/export/${job.export_id}`);
      } else {
        setExportError({
          isEnvelope: false,
          code: null,
          message: "Export endpoint returned no job id.",
          status: null,
          isNetwork: false,
        });
      }
    } catch (err) {
      setExportError(err as NormalizedApiError);
    } finally {
      setExporting(false);
    }
  }

  const columns: Column<TradeRecord>[] = [
    { key: "symbol", header: "Symbol", cell: (r) => <span className="font-medium">{r.symbol}</span>, sortAccessor: (r) => r.symbol },
    { key: "side", header: "Side", cell: (r) => <Chip tone={r.side === "LONG" || r.side === "BUY" ? "emerald" : "rose"}>{r.side}</Chip> },
    { key: "quantity", header: "Qty", numeric: true, cell: (r) => fmtDecimal(r.quantity || "0", 0), sortAccessor: (r) => toNum(r.quantity) },
    { key: "entry_price", header: "Entry", numeric: true, cell: (r) => fmtInr(r.entry_price), sortAccessor: (r) => toNum(r.entry_price) },
    { key: "avg_fill_price", header: "Fill", numeric: true, cell: (r) => fmtInr(r.avg_fill_price), sortAccessor: (r) => toNum(r.avg_fill_price) },
    { key: "realized_pnl", header: "Realized PnL", numeric: true, cell: (r) => <span className={pnlColor(r.realized_pnl)}>{fmtInr(r.realized_pnl)}</span>, sortAccessor: (r) => toNum(r.realized_pnl) },
    { key: "net_pnl", header: "Net PnL", numeric: true, cell: (r) => <span className={pnlColor(r.net_pnl)}>{fmtInr(r.net_pnl)}</span>, sortAccessor: (r) => toNum(r.net_pnl) },
    { key: "status", header: "Status", cell: (r) => <Chip tone={r.status === "FILLED" ? "emerald" : r.status === "REJECTED" ? "rose" : "amber"}>{r.status}</Chip>, sortAccessor: (r) => r.status || "" },
    { key: "created_at", header: "Created", cell: (r) => fmtDateTime(r.created_at), sortAccessor: (r) => r.created_at || "" },
  ];

  return (
    <div className="space-y-4">
      <div className="flex items-baseline justify-between">
        <div>
          <h1 className="text-2xl font-bold text-slate-900">Trade History</h1>
          <p className="text-sm text-slate-500 mt-1">GET /dashboard/trades/history/</p>
        </div>
        <Button variant="secondary" loading={exporting} onClick={handleExport}>
          Request export
        </Button>
      </div>
      {exportError && (
        <Alert tone="error" code={exportError.code} onRetry={() => setExportError(null)}>
          {exportError.message}
        </Alert>
      )}
      {state === "error" && error && (
        <Alert tone="error" code={error.code} onRetry={refetch}>{error.message}</Alert>
      )}
      <Card>
        {state === "loading" ? (
          <DataTable columns={columns} rows={[]} loading rowKey={(_, i) => String(i)} />
        ) : state === "empty" || !data || data.results.length === 0 ? (
          <EmptyState title="No trades" description="There are no trades in this account's history." />
        ) : (
          <DataTable
            columns={columns}
            rows={data.results}
            rowKey={(r, i) => r.trade_id || r.order_id || String(i)}
            initialSortKey="created_at"
            initialSortDir="desc"
            emptyTitle="No trades"
          />
        )}
      </Card>
      {data && data.count > data.results.length && (
        <p className="text-xs text-slate-500">Showing {data.results.length} of {data.count}.</p>
      )}
    </div>
  );
}
