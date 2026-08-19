// Recommendations — GET /recommendations/ + accept/reject/explanation.
// Accept/reject require confirmation modal per 09.

import { useState } from "react";
import { useFetch } from "@/hooks/useFetch";
import { getRecommendations, acceptRecommendation, rejectRecommendation } from "@/api/secondary";
import { Card, Alert, EmptyState, Chip, Button } from "@/components";
import { DataTable, type Column } from "@/components/DataTable";
import { fmtDateTime } from "@/lib/time";
import type { Recommendation } from "@/types/secondary";
import type { NormalizedApiError } from "@/types/common";

export function Recommendations() {
  const { data, state, error, refetch, setData } = useFetch(getRecommendations);
  const [pending, setPending] = useState<Recommendation | null>(null);
  const [action, setAction] = useState<"accept" | "reject" | null>(null);
  const [busy, setBusy] = useState(false);
  const [actionError, setActionError] = useState<NormalizedApiError | null>(null);

  async function confirmAction() {
    if (!pending || !action) return;
    setBusy(true);
    setActionError(null);
    try {
      const updated =
        action === "accept"
          ? await acceptRecommendation(pending.id)
          : await rejectRecommendation(pending.id);
      // Optimistically update the row.
      if (data && Array.isArray(data.results)) {
        setData({
          ...data,
          results: data.results.map((r) => (r.id === pending.id ? { ...r, status: updated.status } : r)),
        });
      }
    } catch (err) {
      setActionError(err as NormalizedApiError);
    } finally {
      setBusy(false);
      setPending(null);
      setAction(null);
    }
  }

  const columns: Column<Recommendation>[] = [
    { key: "id", header: "ID", cell: (r) => <code className="text-[10px]">{r.id.slice(0, 8)}</code>, sortAccessor: (r) => r.id },
    { key: "symbol", header: "Symbol", cell: (r) => r.symbol || "—", sortAccessor: (r) => r.symbol || "" },
    { key: "rule_id", header: "Rule", cell: (r) => r.rule_id ? <Chip tone="violet">{r.rule_id}</Chip> : "—", sortAccessor: (r) => r.rule_id || "" },
    { key: "side", header: "Side", cell: (r) => r.side ? <Chip tone={r.side === "LONG" || r.side === "BUY" ? "emerald" : "rose"}>{r.side}</Chip> : "—" },
    { key: "status", header: "Status", cell: (r) => r.status ? <Chip tone={r.status === "ACCEPTED" ? "emerald" : r.status === "REJECTED" ? "rose" : "amber"}>{r.status}</Chip> : "—", sortAccessor: (r) => r.status || "" },
    { key: "created_at", header: "Created", cell: (r) => fmtDateTime(r.created_at), sortAccessor: (r) => r.created_at || "" },
    {
      key: "actions",
      header: "Actions",
      cell: (r) =>
        r.status === "PENDING" || !r.status ? (
          <div className="flex gap-1">
            <Button variant="secondary" onClick={() => { setPending(r); setAction("accept"); }}>Accept</Button>
            <Button variant="danger" onClick={() => { setPending(r); setAction("reject"); }}>Reject</Button>
          </div>
        ) : (
          <span className="text-xs text-slate-400 dark:text-slate-500 italic">resolved</span>
        ),
    },
  ];

  return (
    <div className="space-y-4">
      <div>
        <h1 className="text-2xl font-bold text-slate-900 dark:text-slate-100">Recommendations</h1>
        <p className="text-sm text-slate-500 dark:text-slate-400 mt-1">GET /recommendations/ · accept/reject require confirmation</p>
      </div>
      <Alert tone="warning" title="⚠ Contract not verified">Body shape not verified.</Alert>
      {state === "error" && error && <Alert tone="error" code={error.code} onRetry={refetch}>{error.message}</Alert>}
      <Card>
        {state === "loading" ? (
          <DataTable columns={columns} rows={[]} loading rowKey={(_, i) => String(i)} />
        ) : !data || data.results.length === 0 ? (
          <EmptyState title="No recommendations" />
        ) : (
          <DataTable columns={columns} rows={data.results} rowKey={(r) => r.id} initialSortKey="created_at" initialSortDir="desc" />
        )}
      </Card>

      {/* Confirmation modal */}
      {pending && action && (
        <div className="fixed inset-0 bg-slate-900/50 flex items-center justify-center z-50 p-4">
          <div className="bg-white dark:bg-slate-900 rounded-lg shadow-xl max-w-md w-full p-6 space-y-4">
            <h2 className="text-lg font-semibold text-slate-900 dark:text-slate-100">
              {action === "accept" ? "Accept recommendation?" : "Reject recommendation?"}
            </h2>
            <p className="text-sm text-slate-600 dark:text-slate-400">
              You are about to {action} recommendation{" "}
              <code className="text-xs">{pending.id.slice(0, 8)}</code>
              {pending.symbol ? ` for ${pending.symbol}` : ""}.
            </p>
            {actionError && (
              <Alert tone="error" code={actionError.code}>{actionError.message}</Alert>
            )}
            <div className="flex justify-end gap-2">
              <Button variant="ghost" onClick={() => { setPending(null); setAction(null); setActionError(null); }} disabled={busy}>
                Cancel
              </Button>
              <Button variant={action === "accept" ? "primary" : "danger"} loading={busy} onClick={confirmAction}>
                Confirm {action}
              </Button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
