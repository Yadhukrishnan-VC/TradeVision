// Shared Analytics layout — extracts accountId from route, shows breadcrumbs,
// and provides sub-nav between PnL / Daily / Performance / Risk.

import { useParams, Link } from "react-router-dom";
import { Breadcrumbs } from "@/components";
import type { ReactNode } from "react";

export function AnalyticsLayout({
  title,
  description,
  children,
}: {
  title: string;
  description: string;
  children: ReactNode;
}) {
  const { accountId } = useParams<{ accountId: string }>();
  if (!accountId) {
    return (
      <div className="space-y-4">
        <Alert>Missing accountId in route.</Alert>
      </div>
    );
  }
  return (
    <div className="space-y-4">
      <Breadcrumbs
        items={[
          { label: "Analytics", to: "/analytics" },
          { label: accountId.slice(0, 8) },
          { label: title },
        ]}
      />
      <div>
        <h1 className="text-2xl font-bold text-slate-900">{title}</h1>
        <p className="text-sm text-slate-500 mt-1">{description}</p>
        <p className="text-xs text-slate-400 mt-1">
          Account <code className="text-[10px]">{accountId}</code>
        </p>
      </div>
      <nav className="flex gap-1 border-b border-slate-200 text-sm">
        {[
          { to: `/analytics/${accountId}/pnl`, label: "PnL" },
          { to: `/analytics/${accountId}/pnl/daily`, label: "Daily Rollup" },
          { to: `/analytics/${accountId}/performance`, label: "Performance" },
          { to: `/analytics/${accountId}/risk`, label: "Risk" },
        ].map((t) => (
          <Link
            key={t.to}
            to={t.to}
            className="px-3 py-1.5 text-slate-600 hover:text-slate-900 border-b-2 border-transparent hover:border-slate-300"
          >
            {t.label}
          </Link>
        ))}
      </nav>
      <div>{children}</div>
    </div>
  );
}

function Alert({ children }: { children: ReactNode }) {
  return (
    <div className="bg-amber-50 border border-amber-200 text-amber-800 px-3 py-2 rounded-md text-sm">
      {children}
    </div>
  );
}
