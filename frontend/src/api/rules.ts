// Rule Engine API module.
// SOURCE: 04_API_CONTRACT.md — /api/v1/rule-engine/.
// ⚠ configs/ and executions/ return BARE arrays (not paginated) — VERIFIED 2026-08-17.
// PATCH /configs/:ruleId/ supports enabled / parameters / severity_override /
//   validated_regimes (merge) — VERIFIED 2026-09-25.

import { apiGet, apiPatch } from "./client";
import type { RuleConfig, RuleConfigUpdate, RuleExecution } from "@/types/rules";

export function getRuleConfigs(): Promise<RuleConfig[]> {
  return apiGet<RuleConfig[]>("/rule-engine/configs/");
}

export function getRuleConfig(ruleId: string): Promise<RuleConfig> {
  return apiGet<RuleConfig>(`/rule-engine/configs/${encodeURIComponent(ruleId)}/`);
}

export function getRuleExecutions(): Promise<RuleExecution[]> {
  return apiGet<RuleExecution[]>("/rule-engine/executions/");
}

/** PATCH rule config — partial update. validated_regimes merges per-regime. */
export function updateRuleConfig(ruleId: string, payload: RuleConfigUpdate): Promise<RuleConfig> {
  return apiPatch<RuleConfig>(`/rule-engine/configs/${encodeURIComponent(ruleId)}/`, payload);
}
