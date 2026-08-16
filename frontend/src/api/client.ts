// Centralized API client for TradeVision frontend.
//
// Implements (per 03_AUTHENTICATION.md, 04_API_CONTRACT.md, 07_DATA_STATES_AND_RESEARCH.md,
// 08_GAPS_BLACKLIST_AND_ASSUMPTIONS.md, 09_SECURITY_AND_GUIDE.md):
//   - Bearer JWT on every request (Authorization: Bearer <access>)
//   - 401 → silent refresh via POST /auth/refresh/ → single retry → else redirect to /login
//   - Both error shapes handled: {error:{code,message}} envelope AND DRF field errors
//   - Paginated envelope {count,next,previous,results} for list endpoints; bare object for research POSTs
//   - Decimals stay strings; never Number() here
//   - No CSRF (token-based, not session cookies)
//   - Manual retry only for POSTs (never auto-retry expensive research jobs)
//
// API-key support is isolated to a separate auth header utility; this client uses
// Bearer JWT only (per user decision #2: Bearer for all normal frontend requests).

import type {
  ApiErrorEnvelope,
  DrfFieldErrors,
  NormalizedApiError,
  Paginated,
} from "@/types/common";
import type { LoginResponse, RefreshResponse } from "@/types/auth";

/** Base URL — relative /api/v1 by default, override via VITE_API_BASE_URL. */
function readBaseUrl(): string {
  // Vite exposes import.meta.env; tsx/Node doesn't. Read defensively.
  try {
    const env = (import.meta as unknown as { env?: Record<string, string | undefined> }).env;
    const v = env?.VITE_API_BASE_URL;
    if (v) return v.replace(/\/$/, "");
  } catch {
    // import.meta.env not available (e.g. running under tsx in Node).
  }
  // Fallback to process.env for non-browser execution contexts.
  if (typeof process !== "undefined" && process.env?.VITE_API_BASE_URL) {
    return process.env.VITE_API_BASE_URL.replace(/\/$/, "");
  }
  return "/api/v1";
}
export const API_BASE_URL: string = readBaseUrl();

/** Sync access to the current access token; set by AuthContext. */
export interface TokenStore {
  getAccess(): string | null;
  getRefresh(): string | null;
  setTokens(access: string, refresh: string): void;
  clearTokens(): void;
}

let tokenStore: TokenStore | null = null;
let onAuthFailure: (() => void) | null = null;

/** Wire the token store + a callback for "refresh failed → /login" navigation. */
export function configureAuth(store: TokenStore, onFail: () => void): void {
  tokenStore = store;
  onAuthFailure = onFail;
}

/** Refresh lock — only one in-flight refresh across all concurrent 401s. */
let refreshPromise: Promise<string | null> | null = null;

async function refreshAccess(): Promise<string | null> {
  if (!tokenStore) return null;
  if (refreshPromise) return refreshPromise;
  const refreshToken = tokenStore.getRefresh();
  if (!refreshToken) {
    triggerAuthFailure();
    return null;
  }
  refreshPromise = (async () => {
    try {
      const res = await fetch(`${API_BASE_URL}/auth/refresh/`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ refresh: refreshToken }),
      });
      if (!res.ok) {
        // 401 invalid_refresh_token → force re-login.
        triggerAuthFailure();
        return null;
      }
      const data = (await res.json()) as RefreshResponse;
      tokenStore.setTokens(data.access, data.refresh);
      return data.access;
    } catch {
      // Network error during refresh — don't necessarily logout, but this
      // request can't proceed.
      return null;
    } finally {
      refreshPromise = null;
    }
  })();
  return refreshPromise;
}

function triggerAuthFailure(): void {
  tokenStore?.clearTokens();
  if (onAuthFailure) onAuthFailure();
}

/** Normalize any error response into a single shape for the UI. */
export async function normalizeError(
  res: Response,
  networkFailure = false
): Promise<NormalizedApiError> {
  if (networkFailure) {
    return {
      isEnvelope: false,
      code: "network_error",
      message: "Cannot reach the server. Check your network and retry.",
      status: null,
      isNetwork: true,
    };
  }
  let body: unknown = null;
  try {
    body = await res.json();
  } catch {
    return {
      isEnvelope: false,
      code: null,
      message: res.statusText || `Request failed (${res.status})`,
      status: res.status,
      isNetwork: false,
    };
  }
  // Shape #1: {error:{code,message,details}}
  if (
    body &&
    typeof body === "object" &&
    "error" in body &&
    body.error &&
    typeof (body as { error: unknown }).error === "object" &&
    "code" in (body as { error: Record<string, unknown> }).error
  ) {
    const env = body as ApiErrorEnvelope;
    return {
      isEnvelope: true,
      code: env.error.code,
      message: env.error.message || "Request failed.",
      status: res.status,
      isNetwork: false,
    };
  }
  // Shape #2: DRF field errors {field:["msg"], detail:"..."}
  if (body && typeof body === "object") {
    const fieldErrors: Record<string, string[]> = {};
    let detail: string | undefined;
    for (const [k, v] of Object.entries(body as Record<string, unknown>)) {
      if (k === "detail" && typeof v === "string") {
        detail = v;
      } else if (Array.isArray(v) && v.every((x) => typeof x === "string")) {
        fieldErrors[k] = v as string[];
      }
    }
    if (detail || Object.keys(fieldErrors).length > 0) {
      return {
        isEnvelope: false,
        code: "validation_error",
        message: detail || "Validation failed.",
        fieldErrors,
        status: res.status,
        isNetwork: false,
      };
    }
  }
  // Fallback: unknown shape; surface raw text.
  return {
    isEnvelope: false,
    code: null,
    message: res.statusText || `Request failed (${res.status})`,
    status: res.status,
    isNetwork: false,
  };
}

/** Fetch wrapper with auth + 401 refresh-retry. */
export async function apiFetch<T = unknown>(
  path: string,
  init: RequestInit = {},
  /** When true, do NOT attempt refresh-on-401 (used by /auth/refresh/ itself). */
  skipAuthRetry = false
): Promise<T> {
  const headers = new Headers(init.headers || {});
  if (!headers.has("Content-Type") && init.body) {
    headers.set("Content-Type", "application/json");
  }
  if (!headers.has("Accept")) {
    headers.set("Accept", "application/json");
  }
  const access = tokenStore?.getAccess();
  if (access) {
    headers.set("Authorization", `Bearer ${access}`);
  }

  let res: Response;
  try {
    res = await fetch(`${API_BASE_URL}${path}`, { ...init, headers });
  } catch {
    throw await normalizeError(new Response(null, { status: 0 }), true);
  }

  if (res.status === 401 && !skipAuthRetry && tokenStore) {
    const newAccess = await refreshAccess();
    if (newAccess) {
      headers.set("Authorization", `Bearer ${newAccess}`);
      try {
        res = await fetch(`${API_BASE_URL}${path}`, { ...init, headers });
      } catch {
        throw await normalizeError(new Response(null, { status: 0 }), true);
      }
    } else {
      triggerAuthFailure();
      throw await normalizeError(res);
    }
  }

  if (!res.ok) {
    throw await normalizeError(res);
  }

  // 204 No Content
  if (res.status === 204) {
    return undefined as T;
  }

  // For application/json, parse and return. (Text/binary callers should use apiRaw.)
  const ct = res.headers.get("content-type") || "";
  if (ct.includes("application/json")) {
    return (await res.json()) as T;
  }
  // Fallback: text.
  return (await res.text()) as unknown as T;
}

/** GET request. */
export function apiGet<T = unknown>(path: string, init?: RequestInit): Promise<T> {
  return apiFetch<T>(path, { ...(init || {}), method: "GET" });
}

/** POST request — never auto-retry (per 08 rule 5). */
export function apiPost<T = unknown>(
  path: string,
  body?: unknown,
  init?: RequestInit
): Promise<T> {
  return apiFetch<T>(path, {
    ...(init || {}),
    method: "POST",
    body: body === undefined ? undefined : JSON.stringify(body),
  });
}

/** DELETE request. */
export function apiDelete<T = void>(path: string, init?: RequestInit): Promise<T> {
  return apiFetch<T>(path, { ...(init || {}), method: "DELETE" });
}

/** PATCH request (only used where the contract documents PATCH — currently watchlist items). */
export function apiPatch<T = unknown>(
  path: string,
  body?: unknown,
  init?: RequestInit
): Promise<T> {
  return apiFetch<T>(path, {
    ...(init || {}),
    method: "PATCH",
    body: body === undefined ? undefined : JSON.stringify(body),
  });
}

/** Paginated GET — unwraps {count,next,previous,results}. */
export async function apiGetPaged<T>(
  path: string,
  init?: RequestInit
): Promise<Paginated<T>> {
  // Returns the raw paginated envelope so the UI can show counts + pagination.
  return apiFetch<Paginated<T>>(path, { ...(init || {}), method: "GET" });
}

// ---- Auth-specific helpers (use skipAuthRetry=true to avoid recursion) ----

export async function postLogin(username: string, password: string): Promise<LoginResponse> {
  return apiFetch<LoginResponse>(
    "/auth/login/",
    {
      method: "POST",
      body: JSON.stringify({ username, password }),
    },
    true
  );
}

export async function postRefresh(refresh: string): Promise<RefreshResponse> {
  return apiFetch<RefreshResponse>(
    "/auth/refresh/",
    {
      method: "POST",
      body: JSON.stringify({ refresh }),
    },
    true
  );
}

/** DrfFieldErrors narrowing helper. */
export function isDrfFieldErrorBody(v: unknown): v is DrfFieldErrors {
  return (
    !!v &&
    typeof v === "object" &&
    Object.values(v as Record<string, unknown>).some(
      (val) => Array.isArray(val) && val.every((x) => typeof x === "string")
    )
  );
}
