// Login page — POST /auth/login/ against the verified contract.
// Per 03_AUTHENTICATION.md: handles invalid_credentials | account_disabled.
// Per 09: never log the password or token.

import { useState, type FormEvent } from "react";
import { useNavigate, useLocation } from "react-router-dom";
import { useAuth } from "@/auth/AuthContext";
import { Alert } from "@/components/Alert";
import { Button } from "@/components/Button";
import type { NormalizedApiError } from "@/types/common";

export function LoginPage() {
  const { user, login } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<NormalizedApiError | null>(null);
  const [loading, setLoading] = useState(false);

  // Already logged in → redirect to where they came from (or /).
  if (user) {
    const from = (location.state as { from?: string } | null)?.from || "/";
    navigate(from, { replace: true });
  }

  async function handleSubmit(e: FormEvent) {
    e.preventDefault();
    if (loading) return;
    setLoading(true);
    setError(null);
    try {
      await login(username, password);
      const from = (location.state as { from?: string } | null)?.from || "/";
      navigate(from, { replace: true });
    } catch (err) {
      setError(err as NormalizedApiError);
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="min-h-screen flex items-center justify-center bg-slate-50 p-4">
      <div className="w-full max-w-md">
        <div className="text-center mb-8">
          <div className="inline-flex items-center justify-center w-12 h-12 rounded-lg bg-indigo-600 text-white font-bold mb-3">
            TV
          </div>
          <h1 className="text-2xl font-bold text-slate-900">TradeVision AI</h1>
          <p className="text-sm text-slate-500 mt-1">
            Rule-based algorithmic trading &amp; research console
          </p>
        </div>

        <form
          onSubmit={handleSubmit}
          className="bg-white border border-slate-200 shadow-sm rounded-lg p-6 space-y-4"
          autoComplete="off"
        >
          <div>
            <label htmlFor="username" className="block text-xs font-medium text-slate-700 mb-1">
              Username
            </label>
            <input
              id="username"
              name="username"
              type="text"
              autoComplete="username"
              required
              autoFocus
              value={username}
              onChange={(e) => setUsername(e.target.value)}
              className="w-full px-3 py-2 text-sm border border-slate-300 rounded-md focus:border-indigo-500 focus:ring-1 focus:ring-indigo-500 outline-none"
              disabled={loading}
            />
          </div>
          <div>
            <label htmlFor="password" className="block text-xs font-medium text-slate-700 mb-1">
              Password
            </label>
            <input
              id="password"
              name="password"
              type="password"
              autoComplete="current-password"
              required
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              className="w-full px-3 py-2 text-sm border border-slate-300 rounded-md focus:border-indigo-500 focus:ring-1 focus:ring-indigo-500 outline-none"
              disabled={loading}
            />
          </div>

          {error && (
            <Alert tone="error" code={error.code} onRetry={() => setError(null)}>
              {error.message}
            </Alert>
          )}

          <Button type="submit" variant="primary" loading={loading} className="w-full">
            Sign in
          </Button>

          <p className="text-[11px] text-slate-400 text-center pt-2">
            Authentication uses Bearer JWT. Session expires after 15 minutes of inactivity.
          </p>
        </form>
      </div>
    </div>
  );
}
