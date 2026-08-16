// Secondary API module — recommendations, signals, pattern-engine, watchlist,
// portfolio (apps/portfolio), risk-management, portfolio-reconciliation,
// trader-memory, ingestion raw-events.
//
// Per decision #7 (watchlist): only GET/DELETE implemented; PATCH deferred.
// Per decision #11 (portfolio fills): POST /portfolio/fills/ omitted entirely.
// Per decision #12 (raw-ingestion): included as a read-only System page.

import { apiDelete, apiGet, apiGetPaged, apiPatch, apiPost } from "./client";
import type { Paginated } from "@/types/common";
import type {
  DriftEntry,
  DriftSummary,
  HistoricalVector,
  IngestionRawEvent,
  KillSwitchState,
  PatternRun,
  PortfolioSummary,
  Recommendation,
  RiskDecision,
  SignalEntry,
  TraderMemoryEntry,
  TraderMemoryProjection,
  WatchlistItem,
} from "@/types/secondary";

// ---- Recommendations ----
export function getRecommendations(): Promise<Paginated<Recommendation>> {
  return apiGetPaged<Recommendation>("/recommendations/");
}
export function getRecommendation(id: string): Promise<Recommendation> {
  return apiGet<Recommendation>(`/recommendations/${encodeURIComponent(id)}/`);
}
export function acceptRecommendation(id: string): Promise<Recommendation> {
  return apiPost<Recommendation>(`/recommendations/${encodeURIComponent(id)}/accept/`);
}
export function rejectRecommendation(id: string): Promise<Recommendation> {
  return apiPost<Recommendation>(`/recommendations/${encodeURIComponent(id)}/reject/`);
}
export function getRecommendationExplanation(id: string): Promise<{ explanation?: string; [k: string]: unknown }> {
  return apiGet(`/recommendations/${encodeURIComponent(id)}/explanation/`);
}

// ---- Signals ----
export function getSignals(): Promise<Paginated<SignalEntry>> {
  return apiGetPaged<SignalEntry>("/signals/");
}
export function getSignal(id: string): Promise<SignalEntry> {
  return apiGet<SignalEntry>(`/signals/${encodeURIComponent(id)}/`);
}

// ---- Pattern Engine ----
export function getPatternRuns(): Promise<Paginated<PatternRun>> {
  return apiGetPaged<PatternRun>("/pattern-engine/runs/");
}
export function getPatternRun(id: string): Promise<PatternRun> {
  return apiGet<PatternRun>(`/pattern-engine/runs/${encodeURIComponent(id)}/`);
}
export function getHistoricalVectors(): Promise<Paginated<HistoricalVector>> {
  return apiGetPaged<HistoricalVector>("/pattern-engine/historical-vectors/");
}

// ---- Watchlist (GET/DELETE only per decision #7; PATCH exported but unused) ----
export function getWatchlist(): Promise<Paginated<WatchlistItem> | WatchlistItem[]> {
  return apiGet<unknown>("/watchlist/").then((res) => {
    if (Array.isArray(res)) return res as WatchlistItem[];
    if (res && typeof res === "object" && "results" in res) {
      return res as Paginated<WatchlistItem>;
    }
    return [];
  });
}
export function deleteWatchlistItem(instrumentToken: number | string): Promise<void> {
  return apiDelete<void>(`/watchlist/${encodeURIComponent(String(instrumentToken))}/`);
}
/** PATCH — exported but DEFERRED until the patch schema is verified. */
export function patchWatchlistItem(
  _instrumentToken: number | string,
  _body: unknown
): Promise<WatchlistItem> {
  // Not implemented until the contract is verified. Throw to prevent accidental use.
  throw new Error("Watchlist PATCH deferred until the request schema is verified.");
}
// (Silence unused-import warning for apiPatch — kept here for future use.)
void apiPatch;

// ---- Portfolio (apps/portfolio) ----
export function getPortfolioSummary(): Promise<PortfolioSummary> {
  return apiGet<PortfolioSummary>("/portfolio/");
}
export function getPortfolioPositions(): Promise<Paginated<unknown>> {
  return apiGetPaged<unknown>("/portfolio/positions/");
}

// ---- Risk Management ----
export function getRiskDecisions(): Promise<Paginated<RiskDecision>> {
  return apiGetPaged<RiskDecision>("/risk-management/decisions/");
}
export function getKillSwitch(): Promise<KillSwitchState> {
  return apiGet<KillSwitchState>("/risk-management/kill-switch/");
}
export function activateKillSwitch(reason?: string): Promise<KillSwitchState> {
  return apiPost<KillSwitchState>("/risk-management/kill-switch/activate/", { reason });
}
export function deactivateKillSwitch(reason?: string): Promise<KillSwitchState> {
  return apiPost<KillSwitchState>("/risk-management/kill-switch/deactivate/", { reason });
}

// ---- Portfolio Reconciliation ----
export function getDriftSummary(): Promise<DriftSummary> {
  return apiGet<DriftSummary>("/portfolio-reconciliation/drift/summary/");
}
export function getDriftList(): Promise<Paginated<DriftEntry>> {
  return apiGetPaged<DriftEntry>("/portfolio-reconciliation/drift/");
}

// ---- Trader Memory ----
export function getTraderMemoryEntries(): Promise<Paginated<TraderMemoryEntry>> {
  return apiGetPaged<TraderMemoryEntry>("/trader-memory/entries/");
}
export function getTraderMemoryProjection(strategyId: string): Promise<TraderMemoryProjection> {
  return apiGet<TraderMemoryProjection>(`/trader-memory/projections/${encodeURIComponent(strategyId)}/`);
}

// ---- Ingestion raw events (secondary, read-only) ----
export function getIngestionRawEvents(): Promise<Paginated<IngestionRawEvent>> {
  return apiGetPaged<IngestionRawEvent>("/ingestion/raw-events/");
}
