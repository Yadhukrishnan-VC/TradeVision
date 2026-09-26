// Strategies — STRATEGY REGISTRY configuration UI.
// GET/POST /strategies/, GET/PATCH/DELETE /strategies/:id/.
// Owner/staff users can create, edit, toggle status, and delete strategies.

import { useState, type FormEvent } from "react";
import { useFetch } from "@/hooks/useFetch";
import { getStrategies, getStrategyAffinities, createStrategy, updateStrategy, deleteStrategy } from "@/api/strategies";
import { Card, Alert, Button, Chip, DataTable, type Column } from "@/components";
import { useAuth } from "@/auth/AuthContext";
import { fmtDateTime } from "@/lib/time";
import type { NormalizedApiError } from "@/types/common";
import type { TradingStrategy, TradingStrategyPayload, StrategyStatus, StrategyProvider, StrategySymbolAffinity } from "@/types/strategies";

const PROVIDERS: Exclude<StrategyProvider, null>[] = ["gemini", "openai", "claude", "ollama", "deepseek"];
const STATUSES: StrategyStatus[] = ["ACTIVE", "INACTIVE", "RETIRED"];

function statusTone(s: StrategyStatus): "emerald" | "slate" | "amber" {
  if (s === "ACTIVE") return "emerald";
  if (s === "RETIRED") return "amber";
  return "slate";
}

export function Strategies() {
  const { user } = useAuth();
  const canManage = user?.role === "owner" || user?.role === "staff";
  const { data, state, error, refetch } = useFetch(getStrategies);
  const [editing, setEditing] = useState<TradingStrategy | null>(null);
  const [creating, setCreating] = useState(false);
  const [actionError, setActionError] = useState<NormalizedApiError | null>(null);
  const [deleting, setDeleting] = useState<TradingStrategy | null>(null);
  const [busy, setBusy] = useState(false);

  const rows: TradingStrategy[] = data || [];

  async function runAction(fn: () => Promise<unknown>) {
    setBusy(true);
    setActionError(null);
    try {
      await fn();
      refetch();
      setEditing(null);
      setCreating(false);
    } catch (err) {
      setActionError(err as NormalizedApiError);
    } finally {
      setBusy(false);
    }
  }

  const columns: Column<TradingStrategy>[] = [
    {
      key: "name",
      header: "Strategy",
      cell: (r) => (
        <div className="flex items-center gap-2">
          <span className="font-medium">{r.name}</span>
          <Chip tone={statusTone(r.status)}>{r.status}</Chip>
        </div>
      ),
      sortAccessor: (r) => r.name,
    },
    { key: "priority", header: "Pri", numeric: true, cell: (r) => r.priority, sortAccessor: (r) => r.priority },
    { key: "provider", header: "Provider", cell: (r) => r.preferred_provider || <span className="text-slate-400 text-xs">default</span>, sortAccessor: (r) => r.preferred_provider || "" },
    { key: "confidence_threshold", header: "Conf.", numeric: true, cell: (r) => <span className="font-mono">{r.confidence_threshold}</span>, sortAccessor: (r) => Number(r.confidence_threshold) },
    { key: "risk_threshold", header: "Risk", numeric: true, cell: (r) => <span className="font-mono">{r.risk_threshold}</span>, sortAccessor: (r) => Number(r.risk_threshold) },
    { key: "filters", header: "Filters", cell: (r) => (
        <span className="text-xs text-slate-500 dark:text-slate-400">
          {r.symbol_filter || r.sector_filter ? [r.symbol_filter, r.sector_filter].filter(Boolean).join(" · ") : "—"}
        </span>
      ) },
    { key: "created_at", header: "Created", cell: (r) => <span className="text-xs text-slate-500 dark:text-slate-400">{fmtDateTime(r.created_at)}</span>, sortAccessor: (r) => r.created_at },
    {
      key: "actions",
      header: "Actions",
      cell: (r) => (
        <div className="flex gap-1" onClick={(e) => e.stopPropagation()}>
          <Button
            variant="ghost"
            className="!px-2 !py-1 text-xs"
            disabled={!canManage}
            onClick={() => { setEditing(r); setCreating(false); setActionError(null); }}
          >
            Edit
          </Button>
          <Button
            variant="ghost"
            className="!px-2 !py-1 text-xs text-rose-600 dark:text-rose-400"
            disabled={!canManage}
            onClick={() => setDeleting(r)}
          >
            Delete
          </Button>
        </div>
      ),
    },
  ];

  return (
    <div className="space-y-4">
      <div className="flex items-start justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold text-slate-900 dark:text-slate-100">Strategies</h1>
          <p className="text-sm text-slate-500 dark:text-slate-400 mt-1">
            GET/POST /strategies/ · active strategies are matched by priority in the StrategyMatcher.
          </p>
        </div>
        {canManage && (
          <Button variant="primary" loading={busy} onClick={() => { setCreating(!creating); setEditing(null); setActionError(null); }}>
            {creating ? "Cancel" : "New strategy"}
          </Button>
        )}
      </div>

      {!canManage && (
        <Alert tone="warning" title="Permission required">
          Only <code>owner</code> or <code>staff</code> roles can create or edit strategies. Your role is{" "}
          <code>{user?.role || "viewer"}</code>.
        </Alert>
      )}

      {actionError && <Alert tone="error" code={actionError.code}>{actionError.message}</Alert>}
      {state === "error" && error && (
        <Alert tone="error" code={error.code} onRetry={refetch}>{error.message}</Alert>
      )}

      {creating && canManage && (
        <StrategyForm
          title="Create strategy"
          submitLabel="Create"
          busy={busy}
          onSubmit={(payload) => runAction(() => createStrategy(payload))}
          onCancel={() => setCreating(false)}
        />
      )}
      {editing && canManage && (
        <StrategyForm
          title={`Edit — ${editing.name}`}
          submitLabel="Save"
          busy={busy}
          initial={editing}
          onSubmit={(payload) => runAction(() => updateStrategy(editing.id, payload))}
          onCancel={() => setEditing(null)}
        />
      )}

      <Card>
        {state === "loading" ? (
          <DataTable columns={columns} rows={[]} loading rowKey={(_, i) => String(i)} />
        ) : rows.length === 0 ? (
          <div className="p-6 text-sm text-slate-500 dark:text-slate-400">
            No strategies. Use the built-in defaults: run{" "}
            <code>python manage.py seed_trading_defaults</code> on the backend.
          </div>
        ) : (
          <DataTable
            columns={columns}
            rows={rows}
            rowKey={(r) => r.id}
            initialSortKey="priority"
            onRowClick={(r) => canManage && setEditing(r)}
          />
        )}
      </Card>

      <AffinitiesPanel />

      {deleting && (
        <div className="fixed inset-0 bg-slate-900/50 flex items-center justify-center z-50 p-4">
          <div className="bg-white dark:bg-slate-900 rounded-lg shadow-xl max-w-md w-full p-6 space-y-4">
            <h2 className="text-lg font-semibold text-slate-900 dark:text-slate-100">Delete strategy?</h2>
            <p className="text-sm text-slate-600 dark:text-slate-400">
              <code>{deleting.name}</code> will be soft-deleted (kept in DB, excluded from matching).
            </p>
            {actionError && <Alert tone="error" code={actionError.code}>{actionError.message}</Alert>}
            <div className="flex justify-end gap-2">
              <Button variant="ghost" onClick={() => setDeleting(null)} disabled={busy}>Cancel</Button>
              <Button variant="danger" loading={busy} onClick={() => runAction(() => deleteStrategy(deleting.id).then(() => setDeleting(null)))}>
                Delete
              </Button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

function StrategyForm({
  title,
  submitLabel,
  busy,
  initial,
  onSubmit,
  onCancel,
}: {
  title: string;
  submitLabel: string;
  busy: boolean;
  initial?: TradingStrategy;
  onSubmit: (payload: TradingStrategyPayload) => void;
  onCancel: () => void;
}) {
  const [name, setName] = useState(initial?.name || "");
  const [status, setStatus] = useState<StrategyStatus>(initial?.status || "INACTIVE");
  const [priority, setPriority] = useState(String(initial?.priority ?? 1));
  const [symbolFilter, setSymbolFilter] = useState(initial?.symbol_filter || "");
  const [sectorFilter, setSectorFilter] = useState(initial?.sector_filter || "");
  const [provider, setProvider] = useState<StrategyProvider>(initial?.preferred_provider || null);
  const [confidence, setConfidence] = useState(initial?.confidence_threshold || "0.6000");
  const [risk, setRisk] = useState(initial?.risk_threshold || "0.5000");

  function submit(e: FormEvent) {
    e.preventDefault();
    onSubmit({
      name,
      status,
      priority: priority === "" ? undefined : Number(priority),
      symbol_filter: symbolFilter.trim() || null,
      sector_filter: sectorFilter.trim() || null,
      preferred_provider: provider,
      confidence_threshold: confidence,
      risk_threshold: risk,
    });
  }

  return (
    <Card title={title}>
      <form onSubmit={submit} className="grid grid-cols-1 md:grid-cols-3 gap-4">
        <Field label="Name">
          <input className="tv-input" value={name} onChange={(e) => setName(e.target.value)} required />
        </Field>
        <Field label="Status">
          <select className="tv-input" value={status} onChange={(e) => setStatus(e.target.value)}>
            {STATUSES.map((s) => <option key={s} value={s}>{s}</option>)}
          </select>
        </Field>
        <Field label="Priority">
          <input className="tv-input" type="number" step="1" value={priority} onChange={(e) => setPriority(e.target.value)} />
        </Field>
        <Field label="Symbol filter">
          <input className="tv-input" placeholder="e.g. NIFTY, RELIANCE" value={symbolFilter} onChange={(e) => setSymbolFilter(e.target.value)} />
        </Field>
        <Field label="Sector filter">
          <input className="tv-input" placeholder="e.g. BANK" value={sectorFilter} onChange={(e) => setSectorFilter(e.target.value)} />
        </Field>
        <Field label="Preferred provider">
          <select className="tv-input" value={provider || ""} onChange={(e) => setProvider((e.target.value || null) as StrategyProvider)}>
            <option value="">default</option>
            {PROVIDERS.map((p) => <option key={p} value={p}>{p}</option>)}
          </select>
        </Field>
        <Field label="Confidence threshold">
          <input className="tv-input" type="number" step="0.05" min="0" max="1" value={confidence} onChange={(e) => setConfidence(e.target.value)} />
        </Field>
        <Field label="Risk threshold">
          <input className="tv-input" type="number" step="0.05" min="0" max="1" value={risk} onChange={(e) => setRisk(e.target.value)} />
        </Field>
        <div className="md:col-span-3 flex justify-end gap-2">
          <Button variant="ghost" type="button" onClick={onCancel} disabled={busy}>Cancel</Button>
          <Button variant="primary" type="submit" loading={busy}>{submitLabel}</Button>
        </div>
      </form>
    </Card>
  );
}

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <label className="block">
      <span className="block text-xs font-medium text-slate-700 dark:text-slate-300 mb-1">{label}</span>
      {children}
    </label>
  );
}

const SYMBOLS = ["TCS", "RELIANCE", "INFY", "HDFCBANK", "ICICIBANK", "SBIN", "LT", "ITC"];

function AffinitiesPanel() {
  const [selected, setSelected] = useState<string>("");
  const { data, state, error, refetch } = useFetch(
    () => getStrategyAffinities(selected || undefined),
    [selected]
  );

  const affinities: StrategySymbolAffinity[] = data || [];
  const symbols = Array.from(new Set(affinities.map((a) => a.symbol))).sort();
  const shown = selected ? symbols.filter((s) => s === selected) : symbols;

  return (
    <Card title="Per-symbol strategy rankings (backtest evidence)">
      <div className="flex flex-wrap items-center gap-2 mb-3">
        <select
          className="tv-input !w-auto"
          value={selected}
          onChange={(e) => setSelected(e.target.value)}
        >
          <option value="">All symbols</option>
          {SYMBOLS.map((s) => (
            <option key={s} value={s}>{s}</option>
          ))}
        </select>
        <Button variant="ghost" className="!px-2 !py-1 text-xs" onClick={refetch} disabled={state === "loading"}>
          Refresh
        </Button>
        <span className="text-xs text-slate-400 ml-auto">
          Matcher prefers rank #1 for a symbol, then global priority.
        </span>
      </div>

      {state === "loading" ? (
        <div className="text-sm text-slate-400">Loading affinities…</div>
      ) : error ? (
        <Alert tone="error" code={error.code} onRetry={refetch}>{error.message}</Alert>
      ) : shown.length === 0 || affinities.length === 0 ? (
        <div className="text-sm text-slate-500 dark:text-slate-400">
          No evidence-backed strategies yet. Backtest runs that clear the gate
          (≥30 trades, expectancy &gt; 0, PF &gt; 1.3, maxDD &lt; 20%) will appear here.
        </div>
      ) : (
        shown.map((sym) => {
          const rows = affinities.filter((a) => a.symbol === sym).sort((a, b) => a.rank - b.rank);
          return (
            <div key={sym} className="mb-4 last:mb-0">
              <h3 className="text-sm font-semibold text-slate-800 dark:text-slate-200 mb-2">{sym}</h3>
              <DataTable
                columns={[
                  { key: "rank", header: "Rank", numeric: true, cell: (r) => <Chip tone={r.rank === 1 ? "emerald" : "slate"}>#{r.rank}</Chip> },
                  { key: "strategy", header: "Strategy", cell: (r) => <span className="font-medium">{r.strategy.name}</span> },
                  { key: "score", header: "Score", numeric: true, cell: (r) => <span className="font-mono">{r.score}</span> },
                  { key: "expectancy", header: "Expectancy", numeric: true, cell: (r) => <span className="font-mono">{r.expectancy ?? "—"}</span> },
                  { key: "pf", header: "PF", numeric: true, cell: (r) => <span className="font-mono">{r.profit_factor ?? "—"}</span> },
                  { key: "dd", header: "MaxDD", numeric: true, cell: (r) => <span className="font-mono">{r.max_drawdown_pct ? `${r.max_drawdown_pct}%` : "—"}</span> },
                  { key: "trades", header: "Trades", numeric: true, cell: (r) => r.trade_count },
                  { key: "evaluated", header: "Evaluated", cell: (r) => <span className="text-xs text-slate-500 dark:text-slate-400">{r.evaluated_at ? fmtDateTime(r.evaluated_at) : "—"}</span> },
                ]}
                rows={rows}
                rowKey={(r) => r.id}
                initialSortKey="rank"
              />
            </div>
          );
        })
      )}
    </Card>
  );
}