// Strategy Registry types.
// SOURCE: GET /api/v1/strategies/ (verified against backend 2026-09-25).

export type StrategyStatus = "ACTIVE" | "INACTIVE" | "RETIRED" | string;

export type StrategyProvider =
  | "gemini"
  | "openai"
  | "claude"
  | "ollama"
  | "deepseek"
  | null;

export interface TradingStrategy {
  id: string;
  name: string;
  status: StrategyStatus;
  priority: number;
  symbol_filter: string | null;
  sector_filter: string | null;
  preferred_provider: StrategyProvider;
  confidence_threshold: string;
  risk_threshold: string;
  created_at: string;
  updated_at: string;
}

export interface TradingStrategyPayload {
  name: string;
  status?: StrategyStatus;
  priority?: number;
  symbol_filter?: string | null;
  sector_filter?: string | null;
  preferred_provider?: StrategyProvider;
  confidence_threshold?: string;
  risk_threshold?: string;
}

export interface StrategySymbolAffinity {
  id: string;
  strategy: TradingStrategy;
  symbol: string;
  rank: number;
  score: string;
  expectancy: string | null;
  profit_factor: string | null;
  sharpe_ratio?: string | null;
  max_drawdown_pct: string | null;
  trade_count: number;
  evaluated_at: string | null;
  created_at: string;
  updated_at: string;
}