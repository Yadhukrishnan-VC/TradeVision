// KillSwitch — GET / POST activate/deactivate /risk-management/kill-switch/.
// Role-gated: owner/staff only. Confirmation modal per 09.

import { useState } from "react";
import { useFetch } from "@/hooks/useFetch";
import { getKillSwitch, activateKillSwitch, deactivateKillSwitch } from "@/api/secondary";
import { Card, Alert, Button, Chip } from "@/components";
import { useAuth } from "@/auth/AuthContext";
import { fmtDateTime } from "@/lib/time";
import type { NormalizedApiError } from "@/types/common";

export function KillSwitch() {
  const { user } = useAuth();
  const canControl = user?.role === "owner" || user?.role === "staff";
  const { data, state, error, refetch, setData } = useFetch(getKillSwitch);
  const [pending, setPending] = useState<"activate" | "deactivate" | null>(null);
  const [reason, setReason] = useState("");
  const [busy, setBusy] = useState(false);
  const [actionError, setActionError] = useState<NormalizedApiError | null>(null);

  async function confirm() {
    if (!pending) return;
    setBusy(true);
    setActionError(null);
    try {
      const updated =
        pending === "activate"
          ? await activateKillSwitch(reason || undefined)
          : await deactivateKillSwitch(reason || undefined);
      setData(updated);
    } catch (err) {
      setActionError(err as NormalizedApiError);
    } finally {
      setBusy(false);
      setPending(null);
      setReason("");
    }
  }

  return (
    <div className="space-y-4">
      <div>
        <h1 className="text-2xl font-bold text-slate-900 dark:text-slate-100">Kill Switch</h1>
        <p className="text-sm text-slate-500 dark:text-slate-400 mt-1">GET/POST /risk-management/kill-switch/</p>
      </div>
      {!canControl && (
        <Alert tone="warning" title="Permission required">
          Only <code>owner</code> or <code>staff</code> roles can activate or
          deactivate the kill switch. Your role is{" "}
          <code>{user?.role || "viewer"}</code>.
        </Alert>
      )}
      {state === "loading" && <Card><div className="h-24 bg-slate-100 dark:bg-slate-800 rounded animate-pulse" /></Card>}
      {state === "error" && error && <Alert tone="error" code={error.code} onRetry={refetch}>{error.message}</Alert>}
      {state === "success" && data && (
        <Card title="Current state">
          <div className="flex items-center gap-3">
            <Chip tone={data.is_active ? "rose" : "emerald"}>
              {data.is_active ? "ACTIVE — trading halted" : "INACTIVE — trading enabled"}
            </Chip>
          </div>
          <dl className="grid grid-cols-2 md:grid-cols-3 gap-3 text-sm mt-4">
            <KV k="Activated at" v={fmtDateTime(data.activated_at)} />
            <KV k="Deactivated at" v={fmtDateTime(data.deactivated_at)} />
            <KV k="Activated by" v={data.activated_by || "—"} />
            <KV k="Reason" v={data.reason || "—"} />
          </dl>
        </Card>
      )}
      {canControl && data && (
        <Card title="Controls">
          <div className="flex gap-2">
            <Button
              variant="danger"
              disabled={data.is_active}
              onClick={() => setPending("activate")}
            >
              Activate kill switch
            </Button>
            <Button
              variant="primary"
              disabled={!data.is_active}
              onClick={() => setPending("deactivate")}
            >
              Deactivate
            </Button>
          </div>
        </Card>
      )}

      {pending && (
        <div className="fixed inset-0 bg-slate-900/50 flex items-center justify-center z-50 p-4">
          <div className="bg-white dark:bg-slate-900 rounded-lg shadow-xl max-w-md w-full p-6 space-y-4">
            <h2 className="text-lg font-semibold text-slate-900 dark:text-slate-100">
              {pending === "activate" ? "Activate kill switch?" : "Deactivate kill switch?"}
            </h2>
            <p className="text-sm text-slate-600 dark:text-slate-400">
              {pending === "activate"
                ? "This will halt all new trading activity. Existing positions are not affected."
                : "This will resume trading activity."}
            </p>
            <label className="block">
              <span className="block text-xs font-medium text-slate-700 dark:text-slate-300 mb-1">Reason (optional)</span>
              <input className="tv-input" value={reason} onChange={(e) => setReason(e.target.value)} disabled={busy} />
            </label>
            {actionError && <Alert tone="error" code={actionError.code}>{actionError.message}</Alert>}
            <div className="flex justify-end gap-2">
              <Button variant="ghost" onClick={() => { setPending(null); setReason(""); setActionError(null); }} disabled={busy}>Cancel</Button>
              <Button variant={pending === "activate" ? "danger" : "primary"} loading={busy} onClick={confirm}>
                Confirm {pending}
              </Button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

function KV({ k, v }: { k: string; v: React.ReactNode }) {
  return (
    <div>
      <dt className="text-xs text-slate-500 dark:text-slate-400">{k}</dt>
      <dd className="text-sm text-slate-900 dark:text-slate-100 mt-0.5">{v || "—"}</dd>
    </div>
  );
}
