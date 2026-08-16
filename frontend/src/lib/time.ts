// Date/time helpers. All timestamps from the API are ISO-8601 (timezone-aware).

export function fmtDateTime(iso: string | null | undefined): string {
  if (!iso) return "--";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  return d.toLocaleString("en-IN", {
    year: "numeric",
    month: "short",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    hour12: false,
    timeZone: "Asia/Kolkata",
  });
}

export function fmtDate(iso: string | null | undefined): string {
  if (!iso) return "--";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  return d.toLocaleDateString("en-IN", {
    year: "numeric",
    month: "short",
    day: "2-digit",
    timeZone: "Asia/Kolkata",
  });
}

export function fmtTimeAgo(iso: string | null | undefined): string {
  if (!iso) return "--";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  const diff = Date.now() - d.getTime();
  const sec = Math.round(diff / 1000);
  if (sec < 60) return `${sec}s ago`;
  const min = Math.round(sec / 60);
  if (min < 60) return `${min}m ago`;
  const hr = Math.round(min / 60);
  if (hr < 24) return `${hr}h ago`;
  const day = Math.round(hr / 24);
  return `${day}d ago`;
}

/** Today's date as YYYY-MM-DD for default form values. */
export function todayDate(): string {
  return new Date().toISOString().slice(0, 10);
}

/** Convert a YYYY-MM-DD input + HH:mm to ISO-8601 UTC. */
export function toIso(date: string, time = "00:00"): string {
  const dt = new Date(`${date}T${time}:00`);
  if (Number.isNaN(dt.getTime())) return "";
  return dt.toISOString();
}
