// Rule Engine + ADR-029 gate types.
// SOURCE: 04_API_CONTRACT.md, 05_DATA_PAGES_AND_IA.md, 07_DATA_STATES_AND_RESEARCH.md.

export type RuleId =
  | "breakout_v1"
  | "high_beta_breakout_v1"
  | "long_momentum_v1"
  | "price_movement_v1"
  | "short_breakdown_v1"
  | "short_sell_v1"
  | "volatility_breakout_v1"
  | "volume_spike_v1"
  | (string & {}); // rules are data-driven; tolerate unknown ids

export type Severity = "LOW" | "MEDIUM" | "HIGH" | "CRITICAL" | string;

/** ADR-029 gate status — stored in RuleConfig.validated_regimes per regime. */
export type GateStatus = "GO" | "NO_GO" | "INSUFFICIENT_DATA" | string;

/**
 * RuleConfig — VERIFIED model field set.
 * `validated_regimes` is a JSON object { "<regime>": "GO"|"NO_GO"|"INSUFFICIENT_DATA" }.
 */
export interface RuleConfig {
  rule_id: RuleId;
  enabled: boolean;
  parameters: Record<string, unknown>;
  severity_override: Severity | null;
  validated_regimes: Record<string, GateStatus>;
  [key: string]: unknown;
}

/** RuleExecution — VERIFIED model field set. */
export interface RuleExecution {
  analysis_event_id: string;
  rule_id: RuleId;
  symbol: string;
  severity: Severity | null;
  trigger_data: {
    regime?: string;
    [key: string]: unknown;
  };
  published_event_id?: string | null;
  created_at?: string | null;
  [key: string]: unknown;
}
