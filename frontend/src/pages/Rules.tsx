// Rules — GET /rule-engine/configs/ + PATCH /rule-engine/configs/:ruleId/.
// ⚠ Body VERIFIED 2026-08-17: bare array. validated_regimes is serialized
//   since 2026-09-25 (per-regime RegimeVerdict). Owner/staff can toggle a rule.

import { useState } from "react";
import { useFetch } from "@/hooks/useFetch";
import { getRuleConfigs, updateRuleConfig } from "@/api/rules";
import { Card, Alert, EmptyState, Chip, Button, gateTone } from "@/components";
import { DataTable, type Column } from "@/components/DataTable";
import { useNavigate } from "react-router-dom";
import type { RuleConfig } from "@/types/rules";
import type { NormalizedApiError } from "@/types/common";

export function Rules() {
  const { data, state, error, refetch } = useFetch(getRuleConfigs);
  const navigate = useNavigate();
  const [busyId, setBusyId] = useState<string | null>(null);
  const [toggleError, setToggleError] = useState<NormalizedApiError | null>(null);

  const rows: RuleConfig[] = data || [];

  async function toggleEnabled(r: RuleConfig) {
    setBusyId(r.rule_id);
    setToggleError(null);
    try {
      await updateRuleConfig(r.rule_id, { enabled: !r.enabled });
      refetch();
    } catch (err) {
      setToggleError(err as NormalizedApiError);
    } finally {
      setBusyId(null);
    }
  }

  const columns: Column<RuleConfig>[] = [
    { key: "rule_id", header: "Rule ID", cell: (r) => <span className="font-medium">{r.rule_id}</span>, sortAccessor: (r) => r.rule_id },
    {
      key: "enabled",
      header: "Enabled",
      cell: (r) => (
        <Button
          variant={r.enabled ? "secondary" : "ghost"}
          className="!px-2 !py-1 text-xs"
          loading={busyId === r.rule_id}
          onClick={(e) => { e.stopPropagation(); toggleEnabled(r); }}
        >
          {r.enabled ? "enabled" : "disabled"}
        </Button>
      ),
      sortAccessor: (r) => (r.enabled ? 1 : 0),
    },
    {
      key: "severity_override",
      header: "Severity",
      cell: (r) => (r.severity_override ? <Chip tone="amber">{r.severity_override}</Chip> : <span className="text-slate-400 dark:text-slate-500 text-xs">default</span>),
      sortAccessor: (r) => r.severity_override || "",
    },
    {
      key: "validated_regimes",
      header: "ADR-029 gate (regimes)",
      cell: (r) => {
        const regimes = Object.entries(r.validated_regimes || {});
        if (regimes.length === 0) return <span className="text-slate-400 text-xs">—</span>;
        return (
          <span className="inline-flex flex-wrap gap-1">
            {regimes.map(([regime, verdict]) => (
              <Chip key={regime} tone={gateTone(verdict?.status)}>
                {regime} {verdict?.status}
              </Chip>
            ))}
          </span>
        );
      },
    },
    {
      key: "parameters",
      header: "Parameters",
      cell: (r) => (
        <code className="text-[10px] text-slate-500 dark:text-slate-400 truncate inline-block max-w-xs">
          {Object.keys(r.parameters || {}).length > 0 ? JSON.stringify(r.parameters) : "{}"}
        </code>
      ),
    },
  ];

  return (
    <div className="space-y-4">
      <div>
        <h1 className="text-2xl font-bold text-slate-900 dark:text-slate-100">Rule Configs</h1>
        <p className="text-sm text-slate-500 dark:text-slate-400 mt-1">
          GET /rule-engine/configs/ · click a row to configure; toggle enables/disables a rule.
        </p>
      </div>
      {state === "error" && error && (
        <Alert tone="error" code={error.code} onRetry={refetch}>{error.message}</Alert>
      )}
      {toggleError && <Alert tone="error" code={toggleError.code}>{toggleError.message}</Alert>}
      <Card>
        {state === "loading" ? (
          <DataTable columns={columns} rows={[]} loading rowKey={(_, i) => String(i)} />
        ) : rows.length === 0 ? (
          <EmptyState title="No rule configs" description="No RuleConfig records returned." />
        ) : (
          <DataTable
            columns={columns}
            rows={rows}
            rowKey={(r) => r.rule_id}
            onRowClick={(r) => navigate(`/rules/${r.rule_id}`)}
            initialSortKey="rule_id"
          />
        )}
      </Card>
    </div>
  );
}