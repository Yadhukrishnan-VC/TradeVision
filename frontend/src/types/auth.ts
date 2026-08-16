// Auth + User + Account types.
// SOURCE: 03_AUTHENTICATION.md, 04_API_CONTRACT.md, 05_DATA_PAGES_AND_IA.md.

export type UserRole = "owner" | "staff" | "viewer";

/**
 * UserSerializer.data — exact field set is ⚠ NOT VERIFIED.
 * We type defensively: every field optional except id+username, render with `--`
 * fallbacks for any missing key.
 */
export interface UserResponse {
  id: string;
  username: string;
  role?: UserRole;
  is_active?: boolean;
  is_staff?: boolean;
  date_joined?: string;
  email?: string;
  first_name?: string;
  last_name?: string;
  /** ⚠ — default account id, mentioned in 05 as "expected from /auth/me/". */
  default_account_id?: string;
  [key: string]: unknown;
}

/** POST /auth/login/ success body. */
export interface LoginResponse {
  access: string;
  refresh: string;
  user: UserResponse;
}

/** POST /auth/refresh/ success body (rotation enabled). */
export interface RefreshResponse {
  access: string;
  refresh: string;
}

/** Login error codes (verified). */
export type LoginErrorCode =
  | "invalid_credentials"
  | "account_disabled"
  | string;

/** Refresh error codes (verified). */
export type RefreshErrorCode = "invalid_refresh_token" | string;

/** API key scopes — enum is in backend `apps/accounts/domain/enums.py` but
 *  NOT enumerated in the markdown package. Treat as string-typed; do not
 *  invent a closed set. */
export type ApiKeyScope = string;

/** /auth/api-keys/ — ⚠ exact body NOT VERIFIED. Defensive interface. */
export interface ApiKey {
  id: string;
  /** Raw key shown ONCE at creation, absent on subsequent reads. */
  raw_key?: string;
  scopes?: ApiKeyScope[];
  /** Optional name/label if the API returns one. */
  name?: string;
  created_at?: string;
  last_used_at?: string | null;
  is_active?: boolean;
  [key: string]: unknown;
}

export interface ApiKeyCreateRequest {
  scopes?: ApiKeyScope[];
  name?: string;
}
