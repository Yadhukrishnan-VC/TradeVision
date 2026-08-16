// RuleExecutions — GET /rule-engine/executions/.

import { useFetch } from "@/hooks/useFetch";
import { getRuleExecutions } from "@/api/rules";
import { Card, Alert, EmptyState, Chip } from "@/components";
import { DataTable, type Column } from "@/components/DataTable";
import { fmtDateTime } from "@/lib/time";
import type { RuleExecution } from "@/types/rules";

export function RuleExecutions() {
  const { data, state, error, refetch } = useFetch(getRuleExecutions);
  const rows: RuleExecution[] = Array.isArray(data) ? data : data?.results || [];

  const columns: Column<RuleExecution>[] = [
    { key: "rule_id", header: "Rule ID", cell: (r) => <Chip tone="violet">{r.rule_id}</Chip>, sortAccessor: (r) => r.rule_id },
    { key: "symbol", header: "Symbol", cell: (r) => <span className="font-medium">{r.symbol}</span>, sortAccessor: (r) => r.symbol },
    {
      key: "severity",
      header: "Severity",
      cell: (r) => r.severity ? <Chip tone={r.severity === "CRITICAL" ? "rose" : r.severity === "HIGH" ? "amber" : "slate"}>{r.severity}</Chip> : <span className="text-slate-400">—</span>,
      sortAccessor: (r) => r.severity || "",
    },
    {
      key: "regime",
      header: "Regime",
      cell: (r) => {
        const regime = (r.trigger_data?.regime) as string | undefined;
        return regime ? <Chip tone="slate">{regime}</Chip> : <span className="text-slate-400">—</span>;
      },
      sortAccessor: (r) => (r.trigger_data?.regime as string) || "",
    },
    {
      key: "analysis_event_id",
      header: "Analysis event",
      cell: (r) => <code className="text-[10px] text-slate-500">{r.analysis_event_id.slice(0, 8)}</code>,
      sortAccessor: (r) => r.analysis_event_id,
    },
    { key: "created_at", header: "Time", cell: (r) => fmtDateTime(r.created_at), sortAccessor: (r) => r.created_at || "" },
  ];

  return (
    <div className="space-y-4">
      <div>
        <h1 className="text-2xl font-bold text-slate-900">Rule Executions</h1>
        <p className="text-sm text-slate-500 mt-1">GET /rule-engine/executions/</p>
      </div>
      <Alert tone="warning" title="⚠ Contract not verified">Body shape not verified.</Alert>
      {state === "error" && error && (
        <Alert tone="error" code={error.code} onRetry={refetch}>{error.message}</Alert>
      )}
      <Card>
        {state === "loading" ? (
          <DataTable columns={columns} rows={[]} loading rowKey={(_, i) => String(i)} />
        ) : rows.length === 0 ? (
          <EmptyState title="No rule executions" />
        ) : (
          <DataTable columns={columns} rows={rows} rowKey={(r) => r.analysis_event_id} initialSortKey="created_at" initialSortDir="desc" />
        )}
      </Card>
    </div>
  );
}
