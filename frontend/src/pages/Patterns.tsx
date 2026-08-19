// Patterns — GET /pattern-engine/runs/ + /historical-vectors/.

import { useFetch } from "@/hooks/useFetch";
import { getPatternRuns, getHistoricalVectors } from "@/api/secondary";
import { Card, Alert, EmptyState, Chip, Tabs, type TabDef } from "@/components";
import { DataTable, type Column } from "@/components/DataTable";
import { fmtDateTime } from "@/lib/time";
import type { PatternRun, HistoricalVector } from "@/types/secondary";

export function Patterns() {
  const runsFetch = useFetch(getPatternRuns);
  const vectorsFetch = useFetch(getHistoricalVectors);

  const runColumns: Column<PatternRun>[] = [
    { key: "id", header: "ID", cell: (r) => <code className="text-[10px]">{r.id.slice(0, 8)}</code>, sortAccessor: (r) => r.id },
    { key: "symbol", header: "Symbol", cell: (r) => r.symbol || "—", sortAccessor: (r) => r.symbol || "" },
    { key: "status", header: "Status", cell: (r) => r.status ? <Chip tone={r.status === "COMPLETED" ? "emerald" : r.status === "FAILED" ? "rose" : "amber"}>{r.status}</Chip> : "—" },
    { key: "pattern_count", header: "Patterns", numeric: true, cell: (r) => r.pattern_count?.toString() || "—", sortAccessor: (r) => r.pattern_count ?? 0 },
    { key: "created_at", header: "Created", cell: (r) => fmtDateTime(r.created_at), sortAccessor: (r) => r.created_at || "" },
  ];

  const vectorColumns: Column<HistoricalVector>[] = [
    { key: "id", header: "ID", cell: (r) => <code className="text-[10px]">{r.id.slice(0, 8)}</code>, sortAccessor: (r) => r.id },
    { key: "symbol", header: "Symbol", cell: (r) => r.symbol || "—", sortAccessor: (r) => r.symbol || "" },
    { key: "timeframe", header: "Timeframe", cell: (r) => r.timeframe || "—" },
    { key: "timestamp", header: "Timestamp", cell: (r) => fmtDateTime(r.timestamp) },
  ];

  const tabs: TabDef[] = [
    {
      key: "runs",
      label: "Runs",
      content: (
        <Card>
          {runsFetch.state === "loading" ? (
            <DataTable columns={runColumns} rows={[]} loading rowKey={(_, i) => String(i)} />
          ) : !runsFetch.data || (Array.isArray(runsFetch.data) ? runsFetch.data.length === 0 : runsFetch.data.results.length === 0) ? (
            <EmptyState title="No pattern runs" />
          ) : (
            <DataTable columns={runColumns} rows={runsFetch.data?.results || []} rowKey={(r) => r.id} initialSortKey="created_at" initialSortDir="desc" />
          )}
        </Card>
      ),
    },
    {
      key: "vectors",
      label: "Historical Vectors",
      content: (
        <Card>
          {vectorsFetch.state === "loading" ? (
            <DataTable columns={vectorColumns} rows={[]} loading rowKey={(_, i) => String(i)} />
          ) : !vectorsFetch.data || vectorsFetch.data.results.length === 0 ? (
            <EmptyState title="No historical vectors" />
          ) : (
            <DataTable columns={vectorColumns} rows={vectorsFetch.data.results} rowKey={(r) => r.id} initialSortKey="timestamp" initialSortDir="desc" />
          )}
        </Card>
      ),
    },
  ];

  return (
    <div className="space-y-4">
      <div>
        <h1 className="text-2xl font-bold text-slate-900 dark:text-slate-100">Pattern Analysis</h1>
        <p className="text-sm text-slate-500 dark:text-slate-400 mt-1">GET /pattern-engine/runs/ + /historical-vectors/</p>
      </div>
      <Alert tone="warning" title="⚠ Contract not verified">Body shape not verified.</Alert>
      {runsFetch.error && <Alert tone="error" code={runsFetch.error.code} onRetry={runsFetch.refetch}>{runsFetch.error.message}</Alert>}
      {vectorsFetch.error && <Alert tone="error" code={vectorsFetch.error.code} onRetry={vectorsFetch.refetch}>{vectorsFetch.error.message}</Alert>}
      <Tabs tabs={tabs} />
    </div>
  );
}
