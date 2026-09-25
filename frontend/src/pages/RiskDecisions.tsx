// RiskDecisions — GET /risk-management/decisions/.

import { useFetch } from "@/hooks/useFetch";
import { getRiskDecisions } from "@/api/secondary";
import { Card, Alert, EmptyState, Chip } from "@/components";
import { DataTable, type Column } from "@/components/DataTable";
import { fmtDateTime } from "@/lib/time";
import type { RiskDecision } from "@/types/secondary";

export function RiskDecisions() {
  const { data, state, error, refetch } = useFetch(getRiskDecisions);

  const decisionOf = (r: RiskDecision) => r.status || r.decision || r.event_type;
  const reasonOf = (r: RiskDecision) => r.reason_message || r.reason || r.rejection_code;

  const columns: Column<RiskDecision>[] = [
    { key: "id", header: "ID", cell: (r) => <code className="text-[10px]">{r.id.slice(0, 8)}</code>, sortAccessor: (r) => r.id },
    { key: "rule_id", header: "Rule", cell: (r) => r.rule_id ? <Chip tone="violet">{r.rule_id.slice(0, 8)}</Chip> : "—", sortAccessor: (r) => r.rule_id || "" },
    { key: "symbol", header: "Symbol", cell: (r) => r.symbol || "—", sortAccessor: (r) => r.symbol || "" },
    { key: "event_type", header: "Event", cell: (r) => r.event_type ? <Chip tone="slate">{r.event_type}</Chip> : "—" },
    { key: "decision", header: "Decision", cell: (r) => decisionOf(r) ? <Chip tone={decisionOf(r) === "REJECTED" ? "rose" : decisionOf(r) === "APPROVED" ? "emerald" : "amber"}>{decisionOf(r)}</Chip> : "—", sortAccessor: (r) => decisionOf(r) || "" },
    { key: "position_size", header: "Qty", numeric: true, cell: (r) => r.position_size !== undefined && r.position_size !== null ? String(r.position_size) : "—", sortAccessor: (r) => Number(r.position_size) },
    { key: "reason_message", header: "Reason", cell: (r) => <span className="text-xs text-slate-600 dark:text-slate-400">{reasonOf(r) || "—"}</span> },
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
