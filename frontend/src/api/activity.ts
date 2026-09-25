// Live activity feed — GET /eventbus/activity/?limit=.
// Realtime view backed by the append-only StoredEvent store.

import { apiGet } from "./client";

export interface ActivityEvent {
  event_id: string;
  event_type: string;
  occurred_at: string;
  version: number;
  payload: Record<string, unknown> | null;
  correlation_id: string;
}

export interface ActivityFeed {
  events: ActivityEvent[];
}

export async function fetchActivity(limit = 60): Promise<ActivityFeed> {
  return apiGet<ActivityFeed>(`/eventbus/activity/?limit=${limit}`);
}

/** Human-readable one-liner for an event's payload. */
export function describePayload(event: ActivityEvent): string {
  const p = event.payload || {};
  if (event.event_type === "broker.ConnectionStatusChanged") {
    return `Broker connection → ${String(p.status ?? "?")}`;
  }
  if (event.event_type === "marketdata.SessionStatusChanged") {
    return `Market session → ${String(p.status ?? "?")}`;
  }
  if (event.event_type === "accounts.UserLoggedIn") {
    return `User ${String(p.username ?? p.user_id ?? "?").slice(0, 8)} logged in`;
  }
  if (event.event_type === "system.HandlerDeadLettered") {
    return `Dead-lettered ${String(p.event_type ?? "?")} (${String(p.failure_reason ?? "?")})`;
  }
  if (/\.(OrderPlaced|OrderFilled|OrderCancelled|OrderRejected)$/.test(event.event_type)) {
    const sym = String(p.symbol ?? p.tradingsymbol ?? p.instrument_token ?? "?");
    return `${event.event_type.split(".").pop()} — ${sym} @ ${String(p.price ?? p.avg_price ?? p.total_quantity ?? "?")}`;
  }
  if (/\.(PositionOpened|PositionClosed)$/.test(event.event_type)) {
    const sym = String(p.symbol ?? p.tradingsymbol ?? "?");
    return `${event.event_type.split(".").pop()} — ${sym} (${String(p.qty ?? p.quantity ?? "?")})`;
  }
  const summary = JSON.stringify(p);
  return summary && summary !== "{}" ? summary.slice(0, 120) : "";
}

/** Generic tone mapping by event type. */
export function toneForType(eventType: string): "emerald" | "amber" | "rose" | "blue" | "slate" | "violet" {
  if (eventType.startsWith("broker.") || eventType.startsWith("execution.")) return "blue";
  if (eventType.startsWith("orders.") || eventType.startsWith("positions.")) return "emerald";
  if (eventType.startsWith("risk.") || eventType.includes("Rejected") || eventType === "system.HandlerDeadLettered") return "rose";
  if (eventType.startsWith("marketdata.") || eventType.startsWith("analytics.")) return "amber";
  if (eventType.startsWith("accounts.")) return "violet";
  return "slate";
}