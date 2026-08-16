// localStorage-backed "recently viewed backtests" — per decision #5, no
// undocumented GET /backtesting/runs/ list endpoint. The SPA tracks run IDs
// the user has created or visited, and shows them as a list panel.

const KEY = "__tv_recent_runs";
const MAX = 20;

export interface RecentRun {
  run_id: string;
  account_id?: string;
  symbol: string;
  timeframe?: string;
  range_start: string;
  range_end: string;
  status: string;
  created_at_locally: number;
  last_viewed_at: number;
}

export function loadRecentRuns(): RecentRun[] {
  try {
    const raw = localStorage.getItem(KEY);
    if (!raw) return [];
    const arr = JSON.parse(raw);
    if (!Array.isArray(arr)) return [];
    return arr as RecentRun[];
  } catch {
    return [];
  }
}

export function saveRecentRun(run: RecentRun): void {
  try {
    const existing = loadRecentRuns().filter((r) => r.run_id !== run.run_id);
    const next = [run, ...existing].slice(0, MAX);
    localStorage.setItem(KEY, JSON.stringify(next));
  } catch {
    // localStorage may be unavailable; silently ignore.
  }
}

export function updateRecentRunStatus(runId: string, status: string): void {
  try {
    const existing = loadRecentRuns();
    const next = existing.map((r) =>
      r.run_id === runId ? { ...r, status, last_viewed_at: Date.now() } : r
    );
    localStorage.setItem(KEY, JSON.stringify(next));
  } catch {
    // ignore
  }
}

export function removeRecentRun(runId: string): void {
  try {
    const next = loadRecentRuns().filter((r) => r.run_id !== runId);
    localStorage.setItem(KEY, JSON.stringify(next));
  } catch {
    // ignore
  }
}
