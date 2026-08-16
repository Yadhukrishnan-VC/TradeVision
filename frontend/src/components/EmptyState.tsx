// EmptyState — icon + message + optional CTA. Used for every null/empty case.

import type { ReactNode } from "react";
import { Inbox } from "lucide-react";

interface EmptyStateProps {
  icon?: ReactNode;
  title: string;
  description?: string;
  action?: ReactNode;
}

export function EmptyState({
  icon,
  title,
  description,
  action,
}: EmptyStateProps) {
  return (
    <div className="flex flex-col items-center justify-center text-center py-10 px-4">
      <div className="text-slate-300 mb-3">
        {icon || <Inbox className="w-10 h-10" />}
      </div>
      <h3 className="text-sm font-semibold text-slate-700">{title}</h3>
      {description && (
        <p className="text-xs text-slate-500 mt-1 max-w-md">{description}</p>
      )}
      {action && <div className="mt-4">{action}</div>}
    </div>
  );
}
