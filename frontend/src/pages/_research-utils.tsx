// Shared research form primitives + synchronous POST hook with 120s timeout.

import { useState, useCallback } from "react";
import type { NormalizedApiError } from "@/types/common";

export interface SyncResearchState<T> {
  loading: boolean;
  data: T | null;
  error: NormalizedApiError | null;
  /** True when the client gave up after 120s but the server may still be computing. */
  timedOut: boolean;
  submit: () => Promise<void>;
  reset: () => void;
}

/**
 * Synchronous-research-POST hook. Per decision #10:
 *   - 120s client timeout
 *   - "still processing" state
 *   - manual retry (NOT auto-retry)
 *   - no fake client-side cancellation (a timeout = client stopped waiting,
 *     server may still be computing)
 */
export function useSyncResearch<T>(
  fetcher: () => Promise<T>,
  options: { timeoutMs?: number } = {}
): SyncResearchState<T> {
  const [loading, setLoading] = useState(false);
  const [data, setData] = useState<T | null>(null);
  const [error, setError] = useState<NormalizedApiError | null>(null);
  const [timedOut, setTimedOut] = useState(false);

  const submit = useCallback(async () => {
    setLoading(true);
    setError(null);
    setTimedOut(false);
    const timeoutMs = options.timeoutMs ?? 120_000;
    let timer: ReturnType<typeof setTimeout> | null = null;
    const timeoutPromise = new Promise<never>((_, reject) => {
      timer = setTimeout(() => {
        setTimedOut(true);
        reject({
          isEnvelope: false,
          code: "client_timeout",
          message:
            "The server is still computing. The client stopped waiting after 120s — you can retry once ready.",
          status: null,
          isNetwork: false,
        } as NormalizedApiError);
      }, timeoutMs);
    });
    try {
      const res = await Promise.race([fetcher(), timeoutPromise]);
      setData(res);
    } catch (err) {
      const e = err as NormalizedApiError;
      setError(e);
    } finally {
      if (timer) clearTimeout(timer);
      setLoading(false);
    }
  }, [fetcher, options.timeoutMs]);

  const reset = useCallback(() => {
    setData(null);
    setError(null);
    setTimedOut(false);
    setLoading(false);
  }, []);

  return { loading, data, error, timedOut, submit, reset };
}

/** Standard labeled field for research forms. */
export function Field({
  label,
  hint,
  children,
}: {
  label: string;
  hint?: string;
  children: React.ReactNode;
}) {
  return (
    <label className="block">
      <span className="block text-xs font-medium text-slate-700 mb-1">{label}</span>
      {children}
      {hint && <span className="block text-[10px] text-slate-400 mt-0.5">{hint}</span>}
    </label>
  );
}

/** Non-blocking warning about backend execution config. */
export function SyncResearchWarning() {
  return (
    <div className="text-[11px] text-slate-500 italic">
      Note: this endpoint runs synchronously. If the backend's Celery is not in
      eager mode, it may hang or fail. The client uses a 120s timeout; manual
      retry only.
    </div>
  );
}

/** Submit button + reset. */
export function ResearchActions({
  loading,
  onReset,
  hasResult,
}: {
  loading: boolean;
  onReset: () => void;
  hasResult: boolean;
}) {
  return (
    <div className="flex items-center justify-end gap-2 pt-2">
      {hasResult && (
        <button
          type="button"
          onClick={onReset}
          disabled={loading}
          className="text-xs text-slate-500 hover:text-slate-700 underline disabled:opacity-50"
        >
          Clear result
        </button>
      )}
      <button
        type="submit"
        disabled={loading}
        className="inline-flex items-center gap-2 px-3 py-2 text-sm font-medium bg-indigo-600 text-white rounded-md hover:bg-indigo-700 disabled:opacity-50 disabled:cursor-not-allowed"
      >
        {loading ? (
          <>
            <span className="w-3.5 h-3.5 border-2 border-white/40 border-t-white rounded-full animate-spin" />
            Computing…
          </>
        ) : (
          "Run analysis"
        )}
      </button>
    </div>
  );
}
