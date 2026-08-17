// System API module — journal, audit, pipeline-health.

import { apiGet, apiGetPaged } from "./client";
import type { Paginated } from "@/types/common";
import type { AuditEntry, JournalEntry, PipelineHealth } from "@/types/secondary";

// ⚠ Journal list returns a BARE array (not paginated) — VERIFIED 2026-08-17.
// `account_id` is required by the backend (400 `missing_account_id` without it).
export function getJournalEntries(accountId?: string): Promise<JournalEntry[]> {
  const q = accountId ? `?account_id=${encodeURIComponent(accountId)}` : "";
  return apiGet<JournalEntry[]>(`/journal/entries/${q}`);
}

export function getJournalEntry(correlationId: string): Promise<JournalEntry> {
  return apiGet<JournalEntry>(`/journal/entries/${encodeURIComponent(correlationId)}/`);
}

export function getAuditEntries(): Promise<Paginated<AuditEntry>> {
  return apiGetPaged<AuditEntry>("/audit/entries/");
}

export function getPipelineHealth(): Promise<PipelineHealth> {
  return apiGet<PipelineHealth>("/pipeline-health/");
}

// Health endpoints (unauthenticated) — used by the System page for status checks.
import { API_BASE_URL } from "./client";

export interface HealthCheck {
  name: string;
  status: "ok" | "fail" | "unknown";
  raw?: unknown;
}

export async function getHealthRoot(): Promise<HealthCheck> {
  try {
    const res = await fetch(`${API_BASE_URL}/health/`);
    return { name: "liveness", status: res.ok ? "ok" : "fail", raw: await res.json().catch(() => null) };
  } catch {
    return { name: "liveness", status: "unknown" };
  }
}

export async function getHealthComponent(name: string): Promise<HealthCheck> {
  try {
    const res = await fetch(`${API_BASE_URL}/health/${name}/`);
    return { name, status: res.ok ? "ok" : "fail", raw: await res.json().catch(() => null) };
  } catch {
    return { name, status: "unknown" };
  }
}
