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

/** Per-regime ADR-029 verdict (RuleConfig.validated_regimes[regime]). */
export interface RegimeVerdict {
  status: GateStatus;
  expectancy: string;
  profit_factor: string;
  sharpe_ratio: string | null;
  max_drawdown_pct: string;
  trade_count: number;
  backtest_run_id: string;
  evaluated_at: string;
  [key: string]: unknown;
}

export type ValidatedRegimes = Record<string, RegimeVerdict>;

/**
 * RuleConfig — VERIFIED against backend (2026-09-25).
 * validated_regimes IS now serialized (per-regime RegimeVerdict objects).
 */
export interface RuleConfig {
  id: string;
  rule_id: RuleId;
  enabled: boolean;
  parameters: Record<string, unknown>;
  severity_override: Severity | null;
  created_at: string;
  updated_at: string;
  validated_regimes: ValidatedRegimes;
  [key: string]: unknown;
}

/** PATCH body for /rule-engine/configs/:ruleId/ — partial, all optional. */
export interface RuleConfigUpdate {
  enabled?: boolean;
  parameters?: Record<string, unknown>;
  severity_override?: Severity | null;
  /** Merge semantic: keys present are upserted; null/"" removes that regime. */
  validated_regimes?: Record<string, RegimeVerdict | null>;
}

/** RuleExecution — VERIFIED against backend (2026-08-17). */
export interface RuleExecution {
  id: string;
  analysis_event_id: string;
  rule_id: RuleId;
  symbol: string;
  severity: Severity | null;
  trigger_data: {
    regime?: string;
    [key: string]: unknown;
  };
  published_event_id: string | null;
  created_at: string;
  [key: string]: unknown;
}
