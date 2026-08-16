// AuthContext — exposes user, role, default account id, login, logout.
// Per 09: access in memory; refresh in localStorage. On 401 → silent refresh
// → single retry → else redirect to /login.

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from "react";
import { configureAuth, postLogin, postRefresh } from "@/api/client";
import { getMe } from "@/api/auth";
import { tokenStore } from "./tokens";
import type { UserResponse } from "@/types/auth";

interface AuthContextValue {
  user: UserResponse | null;
  initializing: boolean;
  login: (username: string, password: string) => Promise<void>;
  logout: () => void;
  /** Refresh the user object (after role change, etc.). */
  refreshUser: () => Promise<void>;
}

const AuthContext = createContext<AuthContextValue | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<UserResponse | null>(null);
  const [initializing, setInitializing] = useState(true);

  // Wire the client's auth-failure callback. When refresh fails, clear tokens
  // and drop user → RequireAuth redirects to /login.
  useEffect(() => {
    configureAuth(tokenStore, () => {
      setUser(null);
    });
  }, []);

  // Boot-time hydration: if a refresh token exists, try to get a fresh access
  // token + fetch /auth/me/. On any failure, clear and stay logged out.
  useEffect(() => {
    let cancelled = false;
    (async () => {
      if (!tokenStore.hasRefresh()) {
        setInitializing(false);
        return;
      }
      try {
        const refresh = tokenStore.getRefresh();
        if (!refresh) {
          setInitializing(false);
          return;
        }
        const tokens = await postRefresh(refresh);
        tokenStore.setTokens(tokens.access, tokens.refresh);
        const me = await getMe();
        if (!cancelled) setUser(me);
      } catch {
        tokenStore.clearTokens();
      } finally {
        if (!cancelled) setInitializing(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  const login = useCallback(async (username: string, password: string) => {
    const res = await postLogin(username, password);
    tokenStore.setTokens(res.access, res.refresh);
    setUser(res.user);
  }, []);

  const logout = useCallback(() => {
    tokenStore.clearTokens();
    setUser(null);
  }, []);

  const refreshUser = useCallback(async () => {
    try {
      const me = await getMe();
      setUser(me);
    } catch {
      // leave existing user intact if a transient failure occurred
    }
  }, []);

  const value = useMemo<AuthContextValue>(
    () => ({ user, initializing, login, logout, refreshUser }),
    [user, initializing, login, logout, refreshUser]
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthContextValue {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth must be used inside <AuthProvider>");
  return ctx;
}
