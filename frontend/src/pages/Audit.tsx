// Audit — GET /audit/entries/. Read-only.

import { useFetch } from "@/hooks/useFetch";
import { getAuditEntries } from "@/api/system";
import { Card, Alert, EmptyState } from "@/components";
import { DataTable, type Column } from "@/components/DataTable";
import { fmtDateTime } from "@/lib/time";
import type { AuditEntry } from "@/types/secondary";

export function Audit() {
  const { data, state, error, refetch } = useFetch(getAuditEntries);

  const columns: Column<AuditEntry>[] = [
    { key: "id", header: "ID", cell: (r) => <code className="text-[10px]">{r.id.slice(0, 8)}</code>, sortAccessor: (r) => r.id },
    { key: "actor", header: "Actor", cell: (r) => r.actor || "—", sortAccessor: (r) => r.actor || "" },
    { key: "action", header: "Action", cell: (r) => r.action || "—", sortAccessor: (r) => r.action || "" },
    { key: "target_type", header: "Target type", cell: (r) => r.target_type || "—", sortAccessor: (r) => r.target_type || "" },
    { key: "target_id", header: "Target ID", cell: (r) => r.target_id ? <code className="text-[10px]">{r.target_id.slice(0, 8)}</code> : "—", sortAccessor: (r) => r.target_id || "" },
    { key: "occurred_at", header: "Time", cell: (r) => fmtDateTime(r.occurred_at), sortAccessor: (r) => r.occurred_at || "" },
  ];

  return (
    <div className="space-y-4">
      <div>
        <h1 className="text-2xl font-bold text-slate-900 dark:text-slate-100">Audit Log</h1>
        <p className="text-sm text-slate-500 dark:text-slate-400 mt-1">GET /audit/entries/ · read-only, authoritative</p>
      </div>
      {state === "error" && error && <Alert tone="error" code={error.code} onRetry={refetch}>{error.message}</Alert>}
      <Card>
        {state === "loading" ? (
          <DataTable columns={columns} rows={[]} loading rowKey={(_, i) => String(i)} />
        ) : !data || data.results.length === 0 ? (
          <EmptyState title="No audit entries" />
        ) : (
          <DataTable columns={columns} rows={data.results} rowKey={(r) => r.id} initialSortKey="occurred_at" initialSortDir="desc" />
        )}
      </Card>
    </div>
  );
}
