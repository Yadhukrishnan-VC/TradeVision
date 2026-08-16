// Journal — GET /journal/entries/ (+ detail by correlationId).

import { useParams, Link } from "react-router-dom";
import { useFetch } from "@/hooks/useFetch";
import { getJournalEntries, getJournalEntry } from "@/api/system";
import { Card, Alert, EmptyState, Chip, Breadcrumbs } from "@/components";
import { DataTable, type Column } from "@/components/DataTable";
import { fmtDateTime } from "@/lib/time";
import type { JournalEntry } from "@/types/secondary";

export function Journal() {
  const { correlationId } = useParams<{ correlationId: string }>();

  if (correlationId) return <JournalDetail correlationId={correlationId} />;
  return <JournalList />;
}

function JournalList() {
  const { data, state, error, refetch } = useFetch(getJournalEntries);

  const columns: Column<JournalEntry>[] = [
    { key: "correlation_id", header: "Correlation ID", cell: (r) => <Link to={`/journal/${r.correlation_id}`} className="text-indigo-600 hover:underline"><code className="text-[10px]">{r.correlation_id.slice(0, 8)}</code></Link>, sortAccessor: (r) => r.correlation_id },
    { key: "entry_type", header: "Type", cell: (r) => r.entry_type ? <Chip tone="slate">{r.entry_type}</Chip> : <span className="text-slate-400">—</span>, sortAccessor: (r) => r.entry_type || "" },
    { key: "symbol", header: "Symbol", cell: (r) => r.symbol || "—", sortAccessor: (r) => r.symbol || "" },
    { key: "rule_id", header: "Rule", cell: (r) => r.rule_id ? <Chip tone="violet">{r.rule_id}</Chip> : <span className="text-slate-400">—</span>, sortAccessor: (r) => r.rule_id || "" },
    { key: "created_at", header: "Time", cell: (r) => fmtDateTime(r.created_at), sortAccessor: (r) => r.created_at || "" },
  ];

  return (
    <div className="space-y-4">
      <div>
        <h1 className="text-2xl font-bold text-slate-900">Trade Journal</h1>
        <p className="text-sm text-slate-500 mt-1">GET /journal/entries/ · read-only</p>
      </div>
      <Alert tone="warning" title="⚠ Contract not verified">Body shape not verified.</Alert>
      {state === "error" && error && <Alert tone="error" code={error.code} onRetry={refetch}>{error.message}</Alert>}
      <Card>
        {state === "loading" ? (
          <DataTable columns={columns} rows={[]} loading rowKey={(_, i) => String(i)} />
        ) : !data || data.results.length === 0 ? (
          <EmptyState title="No journal entries" />
        ) : (
          <DataTable columns={columns} rows={data.results} rowKey={(r) => r.correlation_id} initialSortKey="created_at" initialSortDir="desc" />
        )}
      </Card>
    </div>
  );
}

function JournalDetail({ correlationId }: { correlationId: string }) {
  const { data, state, error, refetch } = useFetch(() => getJournalEntry(correlationId), [correlationId]);

  return (
    <div className="space-y-4">
      <Breadcrumbs
        items={[
          { label: "Journal", to: "/journal" },
          { label: correlationId.slice(0, 8) },
        ]}
      />
      <h1 className="text-2xl font-bold text-slate-900">Journal entry</h1>
      {state === "loading" && <Card><div className="h-24 bg-slate-100 rounded animate-pulse" /></Card>}
      {state === "error" && error && <Alert tone="error" code={error.code} onRetry={refetch}>{error.message}</Alert>}
      {state === "empty" && <Card><EmptyState title="Entry not found" /></Card>}
      {state === "success" && data && (
        <Card title="Entry">
          <dl className="grid grid-cols-2 md:grid-cols-3 gap-3 text-sm">
            <KV k="Correlation ID" v={<code className="text-xs">{data.correlation_id}</code>} />
            <KV k="Entry type" v={data.entry_type || "—"} />
            <KV k="Symbol" v={data.symbol || "—"} />
            <KV k="Rule ID" v={data.rule_id || "—"} />
            <KV k="Severity" v={data.severity || "—"} />
            <KV k="Created at" v={fmtDateTime(data.created_at)} />
          </dl>
          {data.notes && (
            <div className="mt-4 pt-4 border-t border-slate-200">
              <div className="text-xs text-slate-500 mb-1">Notes</div>
              <p className="text-sm text-slate-700">{data.notes}</p>
            </div>
          )}
          {data.payload && (
            <div className="mt-4 pt-4 border-t border-slate-200">
              <div className="text-xs text-slate-500 mb-1">Payload</div>
              <pre className="text-xs text-slate-700 bg-slate-50 p-3 rounded-md overflow-x-auto tv-scrollbar">
                {JSON.stringify(data.payload, null, 2)}
              </pre>
            </div>
          )}
        </Card>
      )}
      <Link to="/journal" className="text-sm text-indigo-600 underline">← Back to journal</Link>
    </div>
  );
}

function KV({ k, v }: { k: string; v: React.ReactNode }) {
  return (
    <div>
      <dt className="text-xs text-slate-500">{k}</dt>
      <dd className="text-sm text-slate-900 mt-0.5">{v || "—"}</dd>
    </div>
  );
}
