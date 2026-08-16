// useFetch — implements the data-state machine per 07_DATA_STATES_AND_RESEARCH.md.
// States: idle | loading | success | error | empty (success with {} / empty results / all-null).
//
// NEVER auto-retry POSTs (per 08 rule 5). For GETs, exposes an explicit `retry` callback.

import { useCallback, useEffect, useRef, useState } from "react";
import type { NormalizedApiError } from "@/types/common";

export type DataState = "idle" | "loading" | "success" | "empty" | "error";

export interface UseFetchResult<T> {
  data: T | null;
  state: DataState;
  error: NormalizedApiError | null;
  refetch: () => void;
  /** Manually set data (optimistic updates / merging). */
  setData: (updater: T | null | ((prev: T | null) => T | null)) => void;
}

export function useFetch<T>(
  fetcher: () => Promise<T>,
  deps: React.DependencyList = [],
  options: { isEmpty?: (data: T) => boolean } = {}
): UseFetchResult<T> {
  const [data, setDataState] = useState<T | null>(null);
  const [state, setState] = useState<DataState>("idle");
  const [error, setError] = useState<NormalizedApiError | null>(null);
  const fetcherRef = useRef(fetcher);
  fetcherRef.current = fetcher;

  const isEmptyFn = options.isEmpty || (() => false);

  const load = useCallback(() => {
    setState("loading");
    setError(null);
    fetcherRef
      .current()
      .then((res: T) => {
        setDataState(res);
        if (isEmptyFn(res)) {
          setState("empty");
        } else {
          setState("success");
        }
      })
      .catch((err: NormalizedApiError) => {
        setError(err);
        setState("error");
      });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, deps);

  useEffect(() => {
    load();
  }, [load]);

  const refetch = useCallback(() => {
    load();
  }, [load]);

  const setData = useCallback(
    (updater: T | null | ((prev: T | null) => T | null)) => {
      setDataState((prev) =>
        typeof updater === "function" ? (updater as (p: T | null) => T | null)(prev) : updater
      );
    },
    []
  );

  return { data, state, error, refetch, setData };
}

/** Convenience: detect "empty" for paginated responses. */
export function isEmptyPaginated(data: unknown): boolean {
  if (!data || typeof data !== "object") return true;
  const r = (data as { results?: unknown[] }).results;
  return Array.isArray(r) && r.length === 0;
}
