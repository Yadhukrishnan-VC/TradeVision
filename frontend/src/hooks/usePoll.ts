// usePoll — polls an async fetcher until a stop condition is met or the timeout elapses.

import { useEffect, useRef, useState } from "react";
import type { NormalizedApiError } from "@/types/common";

interface PollOptions<T> {
  /** Return true to stop polling. */
  shouldStop: (data: T | null) => boolean;
  /** Interval ms (default 2000). */
  intervalMs?: number;
  /** Maximum total duration ms (default 5 min). */
  timeoutMs?: number;
  /** Run immediately on mount (default true). */
  immediate?: boolean;
}

export function usePoll<T>(
  fetcher: () => Promise<T>,
  deps: React.DependencyList,
  options: PollOptions<T>
) {
  const [data, setData] = useState<T | null>(null);
  const [error, setError] = useState<NormalizedApiError | null>(null);
  const [polling, setPolling] = useState<boolean>(true);
  const fetcherRef = useRef(fetcher);
  fetcherRef.current = fetcher;
  const optsRef = useRef(options);
  optsRef.current = options;

  useEffect(() => {
    let cancelled = false;
    let timer: ReturnType<typeof setTimeout> | null = null;
    const startedAt = Date.now();
    const intervalMs = optsRef.current.intervalMs ?? 2000;
    const timeoutMs = optsRef.current.timeoutMs ?? 5 * 60 * 1000;
    const immediate = optsRef.current.immediate ?? true;

    const stop = () => {
      cancelled = true;
      setPolling(false);
      if (timer) clearTimeout(timer);
    };

    const tick = async () => {
      if (cancelled) return;
      if (Date.now() - startedAt > timeoutMs) {
        stop();
        return;
      }
      try {
        const res = await fetcherRef.current();
        if (cancelled) return;
        setData(res);
        setError(null);
        if (optsRef.current.shouldStop(res)) {
          stop();
          return;
        }
      } catch (e) {
        if (cancelled) return;
        setError(e as NormalizedApiError);
        // keep polling on transient errors until timeout
      }
      if (!cancelled) {
        timer = setTimeout(tick, intervalMs);
      }
    };

    if (immediate) tick();
    else {
      timer = setTimeout(tick, intervalMs);
    }

    return () => {
      cancelled = true;
      if (timer) clearTimeout(timer);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, deps);

  return { data, error: error as NormalizedApiError | null, polling, setData };
}
