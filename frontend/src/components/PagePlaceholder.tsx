// PagePlaceholder — used by stub pages during phased implementation.
// Renders a clear "coming soon" state with the route's planned API source.

import { Alert } from "@/components/Alert";
import { Card } from "@/components/Card";
import type { ReactNode } from "react";

interface PagePlaceholderProps {
  title: string;
  /** Route path (for breadcrumb-like context). */
  path: string;
  /** Documented data source(s) — helps reviewers cross-check against 04/05. */
  dataSource: ReactNode;
  /** Implementation phase: P2 = Research, P3 = Dashboard, P4 = Analytics, P5 = Secondary. */
  phase: "P2" | "P3" | "P4" | "P5";
}

export function PagePlaceholder({ title, path, dataSource, phase }: PagePlaceholderProps) {
  return (
    <div className="space-y-4">
      <div>
        <h1 className="text-2xl font-bold text-slate-900 dark:text-slate-100">{title}</h1>
        <code className="text-xs text-slate-500 dark:text-slate-400">{path}</code>
      </div>
      <Alert tone="info" title={`Phase ${phase} — placeholder`}>
        This page is part of the planned phased rollout. It will be wired to its
        documented data source once its phase is reached.
      </Alert>
      <Card title="Documented data source">
        <div className="text-sm text-slate-700 dark:text-slate-300 space-y-1">{dataSource}</div>
      </Card>
    </div>
  );
}
