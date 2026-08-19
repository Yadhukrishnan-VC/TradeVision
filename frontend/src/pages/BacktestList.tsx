// BacktestList page — Phase 2.
// Per decision #5: NO GET /backtesting/runs/ list endpoint is documented.
// The page shows: create form (POST /backtesting/runs/) + a "recently viewed"
// panel powered by localStorage. An explicit notice explains the limitation.

import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { Card } from "@/components/Card";
import { Alert } from "@/components/Alert";
import { Chip, runStatusTone } from "@/components/Chip";
import { EmptyState } from "@/components/EmptyState";
import { BacktestCreateForm } from "./BacktestCreateForm";
import { loadRecentRuns, removeRecentRun, type RecentRun } from "@/lib/recentRuns";
import { fmtDate } from "@/lib/time";
import { Trash2 } from "lucide-react";

export function BacktestList() {
  const [recent, setRecent] = useState<RecentRun[]>([]);

  useEffect(() => {
    setRecent(loadRecentRuns());
  }, []);

  function handleRemoved(runId: string) {
    removeRecentRun(runId);
    setRecent(loadRecentRuns());
  }

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-slate-900 dark:text-slate-100">Backtests</h1>
        <p className="text-sm text-slate-500 dark:text-slate-400 mt-1">
          Create a new backtest run, then poll its status while it executes.
        </p>
      </div>

      <Alert tone="info" title="No list endpoint documented">
        The API contract does not document a <code className="text-xs">GET /backtesting/runs/</code>{" "}
        list endpoint. The "Recently viewed" panel below tracks run IDs you have
        created or opened in this browser. Run IDs persist across sessions in
        localStorage.
      </Alert>

      <Card title="Create new backtest" description="POST /backtesting/runs/">
        <BacktestCreateForm />
      </Card>

      <Card
        title="Recently viewed"
        description={`${recent.length} run${recent.length === 1 ? "" : "s"} tracked locally`}
      >
        {recent.length === 0 ? (
          <EmptyState
            title="No runs tracked yet"
            description="Once you create a backtest, it will appear here for easy return access."
          />
        ) : (
          <ul className="divide-y divide-slate-100">
            {recent.map((r) => (
              <li key={r.run_id} className="py-2 flex items-center justify-between gap-3">
                <Link
                  to={`/research/backtests/${r.run_id}`}
                  className="min-w-0 flex-1 hover:bg-slate-50 rounded -mx-2 px-2 py-1"
                >
                  <div className="flex items-center gap-2 flex-wrap">
                    <span className="font-medium text-slate-900 dark:text-slate-100">{r.symbol}</span>
                    {r.timeframe && (
                      <code className="text-xs text-slate-500 dark:text-slate-400">{r.timeframe}</code>
                    )}
                    <Chip tone={runStatusTone(r.status)}>{r.status}</Chip>
                  </div>
                  <div className="text-xs text-slate-500 dark:text-slate-400 mt-0.5 flex items-center gap-2 flex-wrap">
                    <span>{fmtDate(r.range_start)} → {fmtDate(r.range_end)}</span>
                    <span>·</span>
                    <code className="font-mono text-[10px] text-slate-400 dark:text-slate-500">{r.run_id.slice(0, 8)}</code>
                  </div>
                </Link>
                <button
                  onClick={() => handleRemoved(r.run_id)}
                  className="text-slate-400 dark:text-slate-500 hover:text-rose-600 shrink-0 p-1"
                  aria-label="Remove from recent"
                  title="Remove from recent"
                >
                  <Trash2 className="w-3.5 h-3.5" />
                </button>
              </li>
            ))}
          </ul>
        )}
      </Card>
    </div>
  );
}
