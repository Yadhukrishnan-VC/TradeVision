// Tabs — for Research sub-nav and detail-page sections.

import { useState, type ReactNode } from "react";

export interface TabDef {
  key: string;
  label: ReactNode;
  content: ReactNode;
}

export function Tabs({ tabs, initialKey }: { tabs: TabDef[]; initialKey?: string }) {
  const [active, setActive] = useState<string>(initialKey || tabs[0]?.key || "");
  const current = tabs.find((t) => t.key === active) || tabs[0];
  return (
    <div>
      <div
        className="flex gap-1 border-b border-slate-200 dark:border-slate-800 mb-4 overflow-x-auto"
        role="tablist"
      >
        {tabs.map((t) => (
          <button
            key={t.key}
            role="tab"
            aria-selected={t.key === current?.key}
            onClick={() => setActive(t.key)}
            className={`px-3 py-2 text-sm font-medium whitespace-nowrap border-b-2 -mb-px transition-colors ${
              t.key === current?.key
                ? "border-indigo-600 text-indigo-700 dark:text-indigo-400"
                : "border-transparent text-slate-500 hover:text-slate-700 dark:text-slate-400 dark:hover:text-slate-200"
            }`}
          >
            {t.label}
          </button>
        ))}
      </div>
      <div>{current?.content}</div>
    </div>
  );
}
