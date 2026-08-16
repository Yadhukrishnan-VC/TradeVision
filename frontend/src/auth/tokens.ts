// Token storage — access token in memory (per 09), refresh token in localStorage.
// NEVER log tokens. NEVER expose JWT signing keys (none exist client-side).

const ACCESS_KEY = "__tv_access";
const REFRESH_KEY = "__tv_refresh";

// Access token is kept in a module-private variable; never written to storage.
let accessToken: string | null = null;

export const tokenStore = {
  getAccess(): string | null {
    return accessToken;
  },
  getRefresh(): string | null {
    try {
      return localStorage.getItem(REFRESH_KEY);
    } catch {
      return null;
    }
  },
  setTokens(access: string, refresh: string): void {
    accessToken = access;
    try {
      localStorage.setItem(REFRESH_KEY, refresh);
    } catch {
      // localStorage may be unavailable (private mode); tokens are session-only.
    }
  },
  clearTokens(): void {
    accessToken = null;
    try {
      localStorage.removeItem(REFRESH_KEY);
    } catch {
      // ignore
    }
  },
  // Best-effort hydration on boot: try to refresh using the stored refresh token.
  // Used by AuthContext on mount. Returns null if no refresh token.
  hasRefresh(): boolean {
    try {
      return !!localStorage.getItem(REFRESH_KEY);
    } catch {
      return false;
    }
  },
};

// Mark access key as unused (kept for clarity).
void ACCESS_KEY;
