// RiskDecisions — GET /risk-management/decisions/.

import { useFetch } from "@/hooks/useFetch";
import { getRiskDecisions } from "@/api/secondary";
import { Card, Alert, EmptyState, Chip } from "@/components";
import { DataTable, type Column } from "@/components/DataTable";
import { fmtDateTime } from "@/lib/time";
import type { RiskDecision } from "@/types/secondary";

export function RiskDecisions() {
  const { data, state, error, refetch } = useFetch(getRiskDecisions);

  const columns: Column<RiskDecision>[] = [
    { key: "id", header: "ID", cell: (r) => <code className="text-[10px]">{r.id.slice(0, 8)}</code>, sortAccessor: (r) => r.id },
    { key: "rule_id", header: "Rule", cell: (r) => r.rule_id ? <Chip tone="violet">{r.rule_id}</Chip> : "—", sortAccessor: (r) => r.rule_id || "" },
    { key: "symbol", header: "Symbol", cell: (r) => r.symbol || "—", sortAccessor: (r) => r.symbol || "" },
    { key: "decision", header: "Decision", cell: (r) => r.decision ? <Chip tone={r.decision === "REJECTED" ? "rose" : r.decision === "APPROVED" ? "emerald" : "amber"}>{r.decision}</Chip> : "—", sortAccessor: (r) => r.decision || "" },
    { key: "severity", header: "Severity", cell: (r) => r.severity ? <Chip tone="amber">{r.severity}</Chip> : "—" },
    { key: "reason", header: "Reason", cell: (r) => <span className="text-xs text-slate-600 dark:text-slate-400">{r.reason || "—"}</span> },
    { key: "created_at", header: "Time", cell: (r) => fmtDateTime(r.created_at), sortAccessor: (r) => r.created_at || "" },
  ];

  return (
    <div className="space-y-4">
      <div>
        <h1 className="text-2xl font-bold text-slate-900 dark:text-slate-100">Risk Decisions</h1>
        <p className="text-sm text-slate-500 dark:text-slate-400 mt-1">GET /risk-management/decisions/</p>
      </div>
      <Alert tone="warning" title="⚠ Contract not verified">Body shape not verified.</Alert>
      {state === "error" && error && <Alert tone="error" code={error.code} onRetry={refetch}>{error.message}</Alert>}
      <Card>
        {state === "loading" ? (
          <DataTable columns={columns} rows={[]} loading rowKey={(_, i) => String(i)} />
        ) : !data || data.results.length === 0 ? (
          <EmptyState title="No risk decisions" />
        ) : (
          <DataTable columns={columns} rows={data.results} rowKey={(r) => r.id} initialSortKey="created_at" initialSortDir="desc" />
        )}
      </Card>
    </div>
  );
}
