// LiveActivity — realtime view of the system in motion.
// Polls GET /eventbus/activity/?limit=60 every few seconds and shows the
// most recent domain events plus live broker/session status.

import { useEffect, useRef, useState } from "react";
import { fetchActivity, describePayload, toneForType, type ActivityEvent } from "@/api/activity";
import { Card, Chip, EmptyState, Alert } from "@/components";
import { fmtDateTime } from "@/lib/time";

const POLL_MS = 4000;

export function LiveActivity() {
  const [events, setEvents] = useState<ActivityEvent[]>([]);
  const [liveStatus, setLiveStatus] = useState<string | null>(null);
  const [sessionStatus, setSessionStatus] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [paused, setPaused] = useState(false);
  const [lastRefresh, setLastRefresh] = useState<Date | null>(null);
  const timerRef = useRef<ReturnType<typeof setInterval> | null>(null);

  useEffect(() => {
    const load = async () => {
      if (paused) return;
      try {
        const feed = await fetchActivity(60);
        setEvents(feed.events);
        setError(null);
        for (const ev of feed.events) {
          if (ev.event_type === "broker.ConnectionStatusChanged" && typeof ev.payload?.status === "string") {
            setLiveStatus(String(ev.payload.status));
            break;
          }
          if (ev.event_type === "marketdata.SessionStatusChanged" && typeof ev.payload?.status === "string") {
            setSessionStatus(String(ev.payload.status));
            break;
          }
        }
        setLastRefresh(new Date());
      } catch (e) {
        setError(e instanceof Error ? e.message : "Failed to load activity feed");
      }
    };

    load();
    timerRef.current = setInterval(load, POLL_MS);
    return () => {
      if (timerRef.current) clearInterval(timerRef.current);
    };
  }, [paused]);

  const stats = events.reduce<Record<string, number>>((acc, ev) => {
    const group = ev.event_type.split(".")[0] || "other";
    acc[group] = (acc[group] || 0) + 1;
    return acc;
  }, {});

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between gap-3">
        <div>
          <h1 className="text-2xl font-bold text-slate-900 dark:text-slate-100">Live Activity</h1>
          <p className="text-sm text-slate-500 dark:text-slate-400 mt-1">
            Realtime view — polls GET /eventbus/activity/?limit=60 every {POLL_MS / 1000}s
          </p>
        </div>
        <div className="flex items-center gap-3">
          <span className="inline-flex items-center gap-2 text-sm">
            <span className={`h-2 w-2 rounded-full ${paused ? "bg-slate-400" : "bg-emerald-500 animate-pulse"}`} />
            {paused ? "paused" : "live"}
          </span>
          <button
            onClick={() => setPaused((p) => !p)}
            className="text-xs px-3 py-1.5 rounded-md border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-900 hover:bg-slate-50 dark:hover:bg-slate-800 text-slate-700 dark:text-slate-200"
          >
            {paused ? "Resume" : "Pause"}
          </button>
        </div>
      </div>

      {error && (
        <Alert tone="error" title="Feed error">
          {error}
        </Alert>
      )}

      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
        <Card title="Broker connection" description="Latest broker.ConnectionStatusChanged">
          <div className="flex items-center gap-2">
            <Chip tone={liveStatus === "connected" ? "emerald" : liveStatus === "degraded" ? "amber" : "rose"}>
              {liveStatus ?? "—"}
            </Chip>
          </div>
        </Card>
        <Card title="Market session" description="Latest marketdata.SessionStatusChanged">
          <Chip tone={sessionStatus === "open" ? "emerald" : sessionStatus === "closed" ? "slate" : "amber"}>
            {sessionStatus ?? "—"}
          </Chip>
        </Card>
        <Card title="Event window" description={`Last ${events.length} events across all streams`}>
          <div className="text-sm text-slate-700 dark:text-slate-200">
            {lastRefresh ? `Updated ${fmtDateTime(lastRefresh.toISOString())}` : "Waiting for first poll…"}
          </div>
          <div className="mt-2 flex flex-wrap gap-1.5">
            {Object.entries(stats).map(([k, v]) => (
              <Chip key={k} tone={toneForType(`${k}.x`)}>
                {k}: {v}
              </Chip>
            ))}
          </div>
        </Card>
      </div>

      <Card title="Event stream" description="Most recent published events (newest first)" padded={false}>
        {events.length === 0 ? (
          <div className="p-4">
            <EmptyState title="No events yet" />
          </div>
        ) : (
          <ul className="divide-y divide-slate-100 dark:divide-slate-800">
            {events.map((ev) => (
              <li key={ev.event_id} className="px-4 py-2.5 flex items-start gap-3">
                <div className="w-36 shrink-0">
                  <div className="text-xs font-medium text-slate-900 dark:text-slate-100">
                    {fmtDateTime(ev.occurred_at)}
                  </div>
                  <div className="text-[10px] text-slate-400 mt-0.5 font-mono">{ev.event_id.slice(0, 8)}</div>
                </div>
                <div className="min-w-0 flex-1">
                  <div className="text-xs font-semibold text-slate-700 dark:text-slate-200">
                    <Chip tone={toneForType(ev.event_type)}>{ev.event_type}</Chip>
                    <span className="ml-2 text-slate-500 dark:text-slate-400 font-normal">{describePayload(ev)}</span>
                  </div>
                </div>
              </li>
            ))}
          </ul>
        )}
      </Card>
    </div>
  );
}