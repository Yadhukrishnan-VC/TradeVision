// PortfolioSummary — GET /portfolio/ + POST /portfolio/capital/daily/.

import { useState } from "react";
import { useFetch } from "@/hooks/useFetch";
import {
  getPortfolioPositions,
  getPortfolioSummary,
  setDailyCapital,
} from "@/api/secondary";
import { Card, Alert, EmptyState, StatCard, Button } from "@/components";
import { fmtInr, toNum } from "@/lib/decimal";
import { useAuth } from "@/auth/AuthContext";
import type { NormalizedApiError } from "@/types/common";

export function PortfolioSummary() {
  const { user } = useAuth();
  const canControl = user?.role === "owner" || user?.role === "staff";
  const summary = useFetch(getPortfolioSummary);
  const positions = useFetch(getPortfolioPositions);
  const [target, setTarget] = useState("");
  const [busy, setBusy] = useState(false);
  const [actionError, setActionError] = useState<NormalizedApiError | null>(null);

  async function applyDailyCapital() {
    const amount = Number(target);
    if (!Number.isFinite(amount) || amount <= 0) {
      setActionError({ isEnvelope: false, code: null, message: "Enter a positive amount", status: null, isNetwork: false });
      return;
    }
    setBusy(true);
    setActionError(null);
    try {
      await setDailyCapital(amount);
      setTarget("");
      summary.refetch();
    } catch (err) {
      setActionError(err as NormalizedApiError);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="space-y-4">
      <div>
        <h1 className="text-2xl font-bold text-slate-900 dark:text-slate-100">Portfolio Summary</h1>
        <p className="text-sm text-slate-500 dark:text-slate-400 mt-1">GET /portfolio/ + /portfolio/positions/ (apps/portfolio)</p>
      </div>
      {summary.state === "loading" && <Card><div className="h-24 bg-slate-100 dark:bg-slate-800 rounded animate-pulse" /></Card>}
      {summary.state === "error" && summary.error && <Alert tone="error" code={summary.error.code} onRetry={summary.refetch}>{summary.error.message}</Alert>}
      {summary.state === "empty" && <Card><EmptyState title="No portfolio data" /></Card>}
      {summary.state === "success" && summary.data && (
        <div className="space-y-4">
          <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
            <StatCard label="Equity" value={fmtInr(summary.data.equity)} />
            <StatCard label="Available capital" value={fmtInr(summary.data.available_capital)} />
            <StatCard label="Cash" value={fmtInr(summary.data.cash)} />
            <StatCard label="Margin used" value={fmtInr(summary.data.margin_used)} />
            <StatCard label="Realized PnL today" value={fmtInr(summary.data.realized_pnl_today)} />
            <StatCard label="Unrealized PnL today" value={fmtInr(summary.data.unrealized_pnl_today)} />
          </div>
          <Card title="Daily capital">
            {!canControl && (
              <Alert tone="warning" title="Permission required">
                Only <code>owner</code> or <code>staff</code> roles can set the
                daily capital. Your role is <code>{user?.role || "viewer"}</code>.
              </Alert>
            )}
            {canControl && (
              <div className="flex flex-wrap items-end gap-3">
                <label className="block">
                  <span className="block text-xs font-medium text-slate-700 dark:text-slate-300 mb-1">
                    Target cash (INR)
                  </span>
                  <input
                    className="tv-input"
                    type="number"
                    min="0"
                    step="any"
                    placeholder="e.g. 2000"
                    value={target}
                    onChange={(e) => setTarget(e.target.value)}
                    disabled={busy}
                  />
                </label>
                <Button variant="primary" loading={busy} onClick={applyDailyCapital}>
                  Set daily capital
                </Button>
              </div>
            )}
            {actionError && (
              <Alert tone="error" code={actionError.code}>
                {actionError.message}
              </Alert>
            )}
            <p className="text-xs text-slate-500 dark:text-slate-400 mt-3">
              Sets cash to the target as today's allocation (reason{" "}
              <code>DAILY_ALLOCATION</code>). A 400 means the amount is below
              margin in use.
            </p>
          </Card>
        </div>
      )}
      <Card title="Open positions">
        {positions.state === "error" && positions.error && <Alert tone="error" code={positions.error.code} onRetry={positions.refetch}>{positions.error.message}</Alert>}
        {positions.state === "empty" && <EmptyState title="No open positions" />}
        {positions.state === "success" && positions.data && positions.data.length > 0 && (
          <div className="overflow-x-auto tv-scrollbar max-h-96">
            <table className="min-w-full text-sm">
              <thead>
                <tr className="border-b border-slate-200 dark:border-slate-800 text-xs text-slate-500 dark:text-slate-400">
                  {["Symbol", "Side", "Qty", "Avg entry", "Current", "Unrealized PnL", "Exposure"].map((h) => (
                    <th key={h} className="px-3 py-2 text-left font-semibold">{h}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {positions.data.map((p, i) => (
                  <tr key={i} className="border-b border-slate-100 dark:border-slate-800">
                    <td className="px-3 py-2 font-medium">{p.symbol}</td>
                    <td className="px-3 py-2">{p.side || "—"}</td>
                    <td className="px-3 py-2 font-mono text-right tabular-nums">{p.quantity || "—"}</td>
                    <td className="px-3 py-2 font-mono text-right tabular-nums">{fmtInr(p.avg_entry_price)}</td>
                    <td className="px-3 py-2 font-mono text-right tabular-nums">{p.current_price != null ? fmtInr(p.current_price) : "—"}</td>
                    <td className={`px-3 py-2 font-mono text-right tabular-nums ${toNum(p.unrealized_pnl)! > 0 ? "text-emerald-600" : toNum(p.unrealized_pnl)! < 0 ? "text-rose-600" : "text-slate-500 dark:text-slate-400"}`}>{fmtInr(p.unrealized_pnl)}</td>
                    <td className="px-3 py-2 font-mono text-right tabular-nums">{fmtInr(p.exposure)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Card>
    </div>
  );
}