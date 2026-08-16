// Reconciliation — GET /portfolio-reconciliation/drift/summary/ + /drift/.

import { useFetch } from "@/hooks/useFetch";
import { getDriftSummary, getDriftList } from "@/api/secondary";
import { Card, Alert, EmptyState, StatCard } from "@/components";
import { DataTable, type Column } from "@/components/DataTable";
import { fmtInr, fmtInt } from "@/lib/decimal";
import { fmtDateTime } from "@/lib/time";
import type { DriftEntry } from "@/types/secondary";

export function Reconciliation() {
  const summaryFetch = useFetch(getDriftSummary);
  const driftFetch = useFetch(getDriftList);

  const driftColumns: Column<DriftEntry>[] = [
    { key: "id", header: "ID", cell: (r) => <code className="text-[10px]">{r.id.slice(0, 8)}</code>, sortAccessor: (r) => r.id },
    { key: "symbol", header: "Symbol", cell: (r) => r.symbol || "—", sortAccessor: (r) => r.symbol || "" },
    { key: "expected_quantity", header: "Expected", numeric: true, cell: (r) => r.expected_quantity || "—" },
    { key: "actual_quantity", header: "Actual", numeric: true, cell: (r) => r.actual_quantity || "—" },
    { key: "drift_quantity", header: "Drift qty", numeric: true, cell: (r) => r.drift_quantity || "—" },
    { key: "drift_value", header: "Drift value", numeric: true, cell: (r) => fmtInr(r.drift_value) },
    { key: "detected_at", header: "Detected", cell: (r) => fmtDateTime(r.detected_at), sortAccessor: (r) => r.detected_at || "" },
  ];

  return (
    <div className="space-y-4">
      <div>
        <h1 className="text-2xl font-bold text-slate-900">Portfolio Reconciliation</h1>
        <p className="text-sm text-slate-500 mt-1">GET /portfolio-reconciliation/drift/summary/ + /drift/</p>
      </div>
      <Alert tone="warning" title="⚠ Contract not verified">Body shape not verified.</Alert>

      <div className="grid grid-cols-2 md:grid-cols-3 gap-3">
        <StatCard label="Total drift count" value={fmtInt(summaryFetch.data?.total_drift_count?.toString() || null)} />
        <StatCard label="Total drift value" value={fmtInr(summaryFetch.data?.total_drift_value)} />
        <StatCard label="Last reconciled" value={fmtDateTime(summaryFetch.data?.last_reconciled_at)} />
      </div>

      {summaryFetch.state === "error" && summaryFetch.error && (
        <Alert tone="error" code={summaryFetch.error.code} onRetry={summaryFetch.refetch}>{summaryFetch.error.message}</Alert>
      )}
      {driftFetch.state === "error" && driftFetch.error && (
        <Alert tone="error" code={driftFetch.error.code} onRetry={driftFetch.refetch}>{driftFetch.error.message}</Alert>
      )}

      <Card title="Drift list">
        {driftFetch.state === "loading" ? (
          <DataTable columns={driftColumns} rows={[]} loading rowKey={(_, i) => String(i)} />
        ) : !driftFetch.data || driftFetch.data.results.length === 0 ? (
          <EmptyState title="No drift detected" description="All positions reconcile with expected values." />
        ) : (
          <DataTable columns={driftColumns} rows={driftFetch.data.results} rowKey={(r) => r.id} initialSortKey="detected_at" initialSortDir="desc" />
        )}
      </Card>
    </div>
  );
}
