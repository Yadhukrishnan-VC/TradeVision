// Backtest create form — POST /backtesting/runs/ against the verified contract.

import { useState, type FormEvent } from "react";
import { Button } from "@/components/Button";
import { Alert } from "@/components/Alert";
import { createBacktestRun } from "@/api/research";
import type { BacktestRunCreateRequest } from "@/types/research";
import type { NormalizedApiError } from "@/types/common";
import { useNavigate } from "react-router-dom";
import { todayDate, toIso } from "@/lib/time";
import { saveRecentRun } from "@/lib/recentRuns";

interface Props {
  onCreated?: (runId: string) => void;
}

export function BacktestCreateForm({ onCreated }: Props) {
  const navigate = useNavigate();
  const [symbol, setSymbol] = useState("RELIANCE");
  const [timeframe, setTimeframe] = useState("15min");
  const [rangeStart, setRangeStart] = useState(todayDate());
  const [rangeEnd, setRangeEnd] = useState(todayDate());
  const [initialCapital, setInitialCapital] = useState("1000000");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<NormalizedApiError | null>(null);

  async function handleSubmit(e: FormEvent) {
    e.preventDefault();
    if (loading) return;
    setError(null);
    const range_start = toIso(rangeStart, "00:00");
    const range_end = toIso(rangeEnd, "23:59");
    if (!range_start || !range_end) {
      setError({
        isEnvelope: false,
        code: "validation_error",
        message: "Invalid date range.",
        status: null,
        isNetwork: false,
      });
      return;
    }
    if (new Date(range_end) <= new Date(range_start)) {
      setError({
        isEnvelope: false,
        code: "validation_error",
        message: "range_end must be after range_start.",
        status: null,
        isNetwork: false,
      });
      return;
    }
    const body: BacktestRunCreateRequest = {
      symbol: symbol.toUpperCase(),
      timeframe: timeframe || undefined,
      range_start,
      range_end,
      initial_capital: initialCapital,
    };
    setLoading(true);
    try {
      const res = await createBacktestRun(body);
      saveRecentRun({
        run_id: res.run_id,
        account_id: res.account_id,
        symbol: res.symbol,
        timeframe: res.timeframe,
        range_start: res.range_start,
        range_end: res.range_end,
        status: res.status,
        created_at_locally: Date.now(),
        last_viewed_at: Date.now(),
      });
      if (onCreated) onCreated(res.run_id);
      else navigate(`/research/backtests/${res.run_id}`);
    } catch (err) {
      setError(err as NormalizedApiError);
    } finally {
      setLoading(false);
    }
  }

  return (
    <form onSubmit={handleSubmit} className="space-y-3">
      <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
        <Field label="Symbol">
          <input
            type="text"
            value={symbol}
            onChange={(e) => setSymbol(e.target.value.toUpperCase())}
            required
            className="tv-input"
            disabled={loading}
          />
        </Field>
        <Field label="Timeframe (optional, e.g. 15min, 1D)">
          <input
            type="text"
            value={timeframe}
            onChange={(e) => setTimeframe(e.target.value)}
            className="tv-input"
            disabled={loading}
          />
        </Field>
        <Field label="Range start (date)">
          <input
            type="date"
            value={rangeStart}
            onChange={(e) => setRangeStart(e.target.value)}
            required
            className="tv-input"
            disabled={loading}
          />
        </Field>
        <Field label="Range end (date)">
          <input
            type="date"
            value={rangeEnd}
            onChange={(e) => setRangeEnd(e.target.value)}
            required
            className="tv-input"
            disabled={loading}
          />
        </Field>
        <Field label="Initial capital (₹)">
          <input
            type="text"
            value={initialCapital}
            onChange={(e) => setInitialCapital(e.target.value)}
            className="tv-input font-mono"
            disabled={loading}
          />
        </Field>
      </div>
      {error && (
        <Alert tone="error" code={error.code} onRetry={() => setError(null)}>
          {error.message}
        </Alert>
      )}
      <div className="flex justify-end gap-2">
        <Button type="submit" variant="primary" loading={loading}>
          Run backtest
        </Button>
      </div>
    </form>
  );
}

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <label className="block">
      <span className="block text-xs font-medium text-slate-700 mb-1">{label}</span>
      {children}
    </label>
  );
}
