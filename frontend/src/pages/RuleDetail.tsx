// RuleDetail — GET/PATCH /rule-engine/configs/:ruleId/.
// Owner/staff can toggle enabled, set severity override, edit JSON parameters,
// and override the ADR-029 gate status per regime. Regime verdicts PATCH with
// merge semantics (missing regimes are untouched; null removes a regime).

import { useState } from "react";
import { useParams, Link } from "react-router-dom";
import { useFetch } from "@/hooks/useFetch";
import { getRuleConfig, updateRuleConfig } from "@/api/rules";
import { Card, Alert, Breadcrumbs, EmptyState, Chip, Button } from "@/components";
import { useAuth } from "@/auth/AuthContext";
import type { NormalizedApiError } from "@/types/common";
import type { RuleConfig, RuleConfigUpdate, GateStatus, Severity, RegimeVerdict } from "@/types/rules";

const REGIME_OPTIONS = ["RANGING", "BULLISH", "BEARISH", "VOLATILE", "BREAKOUT", "BREAKDOWN"];
const SEVERITIES: Severity[] = ["LOW", "MEDIUM", "HIGH", "CRITICAL"];
const GATE_OPTIONS: GateStatus[] = ["GO", "NO_GO", "INSUFFICIENT_DATA"];

export function RuleDetail() {
  const { ruleId } = useParams<{ ruleId: string }>();
  const { user } = useAuth();
  const canManage = user?.role === "owner" || user?.role === "staff";
  const rid = ruleId || "";
  const { data, state, error, refetch } = useFetch(() => getRuleConfig(rid), [rid]);

  const [busy, setBusy] = useState(false);
  const [actionError, setActionError] = useState<NormalizedApiError | null>(null);

  function patch(payload: RuleConfigUpdate) {
    setBusy(true);
    setActionError(null);
    updateRuleConfig(rid, payload)
      .then(refetch)
      .catch((err: NormalizedApiError) => setActionError(err))
      .finally(() => setBusy(false));
  }

  return (
    <div className="space-y-4">
      <Breadcrumbs
        items={[
          { label: "Rules", to: "/rules" },
          { label: rid || "—" },
        ]}
      />
      <h1 className="text-2xl font-bold text-slate-900 dark:text-slate-100">Rule — {rid}</h1>

      {state === "loading" && <Card><div className="h-24 bg-slate-100 dark:bg-slate-800 rounded animate-pulse" /></Card>}
      {state === "error" && error && <Alert tone="error" code={error.code} onRetry={refetch}>{error.message}</Alert>}
      {state === "empty" && <Card><EmptyState title="Rule not found" /></Card>}

      {state === "success" && data && (
        <div className="space-y-4">
          {!canManage && (
            <Alert tone="warning" title="Read only">
              Only <code>owner</code> or <code>staff</code> can modify rule configs. Your role is{" "}
              <code>{user?.role || "viewer"}</code>.
            </Alert>
          )}
          {actionError && <Alert tone="error" code={actionError.code}>{actionError.message}</Alert>}

          <Card title="Configuration" description="PATCH /rule-engine/configs/:ruleId/">
            <dl className="grid grid-cols-1 md:grid-cols-3 gap-3 text-sm">
              <div>
                <dt className="text-xs text-slate-500 dark:text-slate-400">Rule ID</dt>
                <dd className="mt-0.5"><Chip tone="violet">{data.rule_id}</Chip></dd>
              </div>
              <div>
                <dt className="text-xs text-slate-500 dark:text-slate-400">Enabled</dt>
                <dd className="mt-0.5 flex items-center gap-2">
                  <Chip tone={data.enabled ? "emerald" : "slate"}>{String(data.enabled)}</Chip>
                  <Button
                    variant="secondary"
                    className="!px-2 !py-1 text-xs"
                    disabled={!canManage}
                    loading={busy}
                    onClick={() => patch({ enabled: !data.enabled })}
                  >
                    {data.enabled ? "Disable" : "Enable"}
                  </Button>
                </dd>
              </div>
              <div>
                <dt className="text-xs text-slate-500 dark:text-slate-400">Severity override</dt>
                <dd className="mt-0.5">
                  <select
                    className="tv-input"
                    value={data.severity_override || ""}
                    disabled={!canManage || busy}
                    onChange={(e) => patch({ severity_override: (e.target.value || null) as Severity })}
                  >
                    <option value="">default</option>
                    {SEVERITIES.map((s) => <option key={s} value={s}>{s}</option>)}
                  </select>
                </dd>
              </div>
            </dl>
          </Card>

          <Card title="ADR-029 validation gate" description="Per-regime GO/NO_GO verdicts drive the rule firing gate">
            <div className="space-y-2">
              {Object.keys(data.validated_regimes || {}).length === 0 && (
                <p className="text-sm text-slate-500 dark:text-slate-400">
                  No validated regimes yet — the gate will not fire. Add one below.
                </p>
              )}
              {Object.entries(data.validated_regimes || {}).map(([regime, verdict]) => (
                <RegimeEditor
                  key={regime}
                  regime={regime}
                  verdict={verdict}
                  canManage={canManage}
                  busy={busy}
                  onStatus={(next: GateStatus) => patch({
                    validated_regimes: { [regime]: { ...verdict, status: next } },
                  })}
                  onRemove={() => patch({ validated_regimes: { [regime]: null } })}
                />
              ))}
              {canManage && (
                <AddRegime config={data} busy={busy} onAdd={(regime) => {
                  const now = new Date().toISOString();
                  patch({
                    validated_regimes: {
                      [regime]: {
                        status: "INSUFFICIENT_DATA",
                        expectancy: "0.00000000",
                        profit_factor: "1.30",
                        sharpe_ratio: null,
                        max_drawdown_pct: "0.0000",
                        trade_count: 0,
                        backtest_run_id: "manual_patch",
                        evaluated_at: now,
                      } satisfies RegimeVerdict,
                    },
                  });
                }} />
              )}
            </div>
          </Card>

          <ParametersEditor config={data} canManage={canManage} busy={busy} onSave={(parameters) => patch({ parameters })} />

          <Link to="/rules" className="text-sm text-indigo-600 underline">← Back to rules</Link>
        </div>
      )}
    </div>
  );
}

function RegimeEditor({
  regime,
  verdict,
  canManage,
  busy,
  onStatus,
  onRemove,
}: {
  regime: string;
  verdict: RegimeVerdict;
  canManage: boolean;
  busy: boolean;
  onStatus: (s: GateStatus) => void;
  onRemove: () => void;
}) {
  return (
    <div className="flex flex-wrap items-center gap-3 border border-slate-200 dark:border-slate-800 rounded-md px-3 py-2">
      <Chip tone="indigo" className="!text-sm">{regime}</Chip>
      <select
        className="tv-input !w-auto !py-1"
        value={verdict.status}
        disabled={!canManage || busy}
        onChange={(e) => onStatus(e.target.value as GateStatus)}
      >
        {GATE_OPTIONS.map((s) => (
          <option key={s} value={s}>{s}</option>
        ))}
      </select>
      <span className="text-xs text-slate-500 dark:text-slate-400">
        expectancy {verdict.expectancy} · PF {verdict.profit_factor} · {verdict.trade_count} trades
      </span>
      <span className="text-xs font-mono text-slate-400 dark:text-slate-500">
        {String(verdict.backtest_run_id || "unverified")}
      </span>
      {canManage && (
        <Button variant="ghost" className="!px-2 !py-1 text-xs text-rose-600 dark:text-rose-400" disabled={busy} onClick={onRemove}>
          Remove
        </Button>
      )}
    </div>
  );
}

function AddRegime({ config, busy, onAdd }: { config: RuleConfig; busy: boolean; onAdd: (r: string) => void }) {
  const present = new Set(Object.keys(config.validated_regimes || {}));
  const available = REGIME_OPTIONS.filter((r) => !present.has(r));
  const [pick, setPick] = useState("");
  return (
    <div className="flex items-center gap-2 pt-1">
      <select className="tv-input !w-auto" value={pick} onChange={(e) => setPick(e.target.value)}>
        <option value="">Add regime…</option>
        {available.map((r) => <option key={r} value={r}>{r}</option>)}
      </select>
      <Button
        variant="secondary"
        className="!px-2 !py-1 text-xs"
        disabled={!pick || busy}
        loading={busy}
        onClick={() => { onAdd(pick); setPick(""); }}
      >
        Add
      </Button>
    </div>
  );
}

function ParametersEditor({
  config,
  canManage,
  busy,
  onSave,
}: {
  config: RuleConfig;
  canManage: boolean;
  busy: boolean;
  onSave: (parameters: Record<string, unknown>) => void;
}) {
  const [text, setText] = useState(JSON.stringify(config.parameters || {}, null, 2));
  const [parseError, setParseError] = useState<string | null>(null);

  function save() {
    try {
      const parsed = JSON.parse(text);
      setParseError(null);
      onSave(parsed);
    } catch {
      setParseError("Invalid JSON — check syntax before saving.");
    }
  }

  return (
    <Card title="Parameters" description="JSON — saved via PATCH parameters">
      <textarea
        className="tv-input font-mono text-xs h-40"
        value={text}
        disabled={!canManage || busy}
        onChange={(e) => { setText(e.target.value); setParseError(null); }}
      />
      <div className="flex items-center gap-3 mt-2">
        {canManage && <Button variant="primary" className="!px-3 !py-1 text-xs" loading={busy} onClick={save}>Save parameters</Button>}
        {parseError && <span className="text-xs text-rose-600 dark:text-rose-400">{parseError}</span>}
      </div>
    </Card>
  );
}