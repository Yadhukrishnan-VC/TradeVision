// Reconciliation — GET /portfolio-reconciliation/drift/summary/ + /drift/.

import { useFetch } from "@/hooks/useFetch";
import { getDriftSummary, getDriftList } from "@/api/secondary";
import { Card, Alert, EmptyState, StatCard, Chip } from "@/components";
import { DataTable, type Column } from "@/components/DataTable";
import { fmtInt } from "@/lib/decimal";
import { fmtDateTime } from "@/lib/time";
import type { DriftEntry } from "@/types/secondary";

const CLASS_TONE: Record<string, "rose" | "amber" | "emerald" | "violet" | "slate"> = {
  missing: "rose",
  extra: "amber",
  qty_drift: "amber",
  price_drift: "amber",
  position_drift: "amber",
  auto_repaired: "emerald",
  ok: "emerald",
};

function symbolOf(entry: DriftEntry): string {
  if (entry.entity_type === "position" && typeof entry.entity_key === "string") {
    const parts = entry.entity_key.split(":");
    if (parts.length > 1) return parts[parts.length - 1];
  }
  return entry.entity_key || "—";
}

export function Reconciliation() {
  const summaryFetch = useFetch(getDriftSummary);
  const driftFetch = useFetch(getDriftList);

  const driftColumns: Column<DriftEntry>[] = [
    { key: "id", header: "ID", cell: (r) => <code className="text-[10px]">{r.id.slice(0, 8)}</code>, sortAccessor: (r) => r.id },
    { key: "symbol", header: "Entity", cell: (r) => symbolOf(r), sortAccessor: (r) => symbolOf(r) },
    { key: "entity_type", header: "Type", cell: (r) => <Chip tone="slate">{r.entity_type || "—"}</Chip> },
    { key: "classification", header: "Classification", cell: (r) => <Chip tone={CLASS_TONE[r.classification || ""] || "slate"}>{r.classification || "—"}</Chip> },
    { key: "auto_repaired", header: "Auto-repaired", cell: (r) => (r.auto_repaired ? "Yes" : "No") },
    { key: "detected_at", header: "Detected", cell: (r) => fmtDateTime(r.detected_at), sortAccessor: (r) => r.detected_at || "" },
    {
      key: "snapshots",
      header: "Expected / actual",
      cell: (r) => (
        <div className="font-mono text-[10px] leading-tight">
          <div className="text-emerald-600 dark:text-emerald-400">{JSON.stringify(r.expected_snapshot || {})}</div>
          <div className="text-rose-600 dark:text-rose-400">{JSON.stringify(r.actual_snapshot || {})}</div>
        </div>
      ),
    },
  ];

  const summary = summaryFetch.data;
  const totalRecords = summary?.total_records ?? summary?.total_drift_count;
  const lastRun = summary?.last_run_at ?? summary?.last_reconciled_at;

  return (
    <div className="space-y-4">
      <div>
        <h1 className="text-2xl font-bold text-slate-900 dark:text-slate-100">Portfolio Reconciliation</h1>
        <p className="text-sm text-slate-500 dark:text-slate-400 mt-1">GET /portfolio-reconciliation/drift/summary/ + /drift/</p>
      </div>

      <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
        <StatCard label="Drift records" value={fmtInt((totalRecords ?? 0).toString())} />
        <StatCard label="Last reconciled" value={fmtDateTime(lastRun)} />
        <div className="md:col-span-2">
          <Card title="By classification" padded>
            {summary?.classification_breakdown && Object.keys(summary.classification_breakdown).length > 0 ? (
              <div className="flex flex-wrap gap-1.5">
                {Object.entries(summary.classification_breakdown).map(([k, v]) => (
                  <Chip key={k} tone={CLASS_TONE[k] || "slate"}>
                    {k}: {v}
                  </Chip>
                ))}
              </div>
            ) : (
              <div className="text-sm text-slate-500 dark:text-slate-400 italic">No breakdown available</div>
            )}
          </Card>
        </div>
      </div>

      {summaryFetch.state === "error" && summaryFetch.error && (
        <Alert tone="error" code={summaryFetch.error.code} onRetry={summaryFetch.refetch}>{summaryFetch.error.message}</Alert>
      )}
      {driftFetch.state === "error" && driftFetch.error && (
        <Alert tone="error" code={driftFetch.error.code} onRetry={driftFetch.refetch}>{driftFetch.error.message}</Alert>
      )}

      <Card title="Drift list" padded={false}>
        {driftFetch.state === "loading" ? (
          <DataTable columns={driftColumns} rows={[]} loading rowKey={(_, i) => String(i)} />
        ) : !driftFetch.data || driftFetch.data.results.length === 0 ? (
          <div className="p-4">
            <EmptyState title="No drift detected" description="All positions reconcile with expected values." />
          </div>
        ) : (
          <DataTable columns={driftColumns} rows={driftFetch.data.results} rowKey={(r) => r.id} initialSortKey="detected_at" initialSortDir="desc" />
        )}
      </Card>
    </div>
  );
}