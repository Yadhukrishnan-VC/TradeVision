// Alert — inline error banner using error.code/message from the API envelope.

import type { ReactNode } from "react";
import { AlertCircle, AlertTriangle, Info, XCircle } from "lucide-react";

type Tone = "error" | "warning" | "info" | "success";

const TONES: Record<Tone, { wrap: string; icon: ReactNode }> = {
  error: {
    wrap: "bg-rose-50 border-rose-200 text-rose-800 dark:bg-rose-950/40 dark:border-rose-900 dark:text-rose-300",
    icon: <XCircle className="w-4 h-4 text-rose-600 dark:text-rose-400" />,
  },
  warning: {
    wrap: "bg-amber-50 border-amber-200 text-amber-800 dark:bg-amber-950/40 dark:border-amber-900 dark:text-amber-300",
    icon: <AlertTriangle className="w-4 h-4 text-amber-600 dark:text-amber-400" />,
  },
  info: {
    wrap: "bg-blue-50 border-blue-200 text-blue-800 dark:bg-blue-950/40 dark:border-blue-900 dark:text-blue-300",
    icon: <Info className="w-4 h-4 text-blue-600 dark:text-blue-400" />,
  },
  success: {
    wrap: "bg-emerald-50 border-emerald-200 text-emerald-800 dark:bg-emerald-950/40 dark:border-emerald-900 dark:text-emerald-300",
    icon: <AlertCircle className="w-4 h-4 text-emerald-600 dark:text-emerald-400" />,
  },
};

interface AlertProps {
  tone?: Tone;
  title?: ReactNode;
  children?: ReactNode;
  code?: string | null;
  onRetry?: () => void;
}

export function Alert({
  tone = "error",
  title,
  children,
  code,
  onRetry,
}: AlertProps) {
  const t = TONES[tone];
  return (
    <div className={`flex items-start gap-2 px-3 py-2 border rounded-md text-sm ${t.wrap}`}>
      <div className="shrink-0 mt-0.5">{t.icon}</div>
      <div className="min-w-0 flex-1">
        {title && <div className="font-semibold">{title}</div>}
        <div className={title ? "text-xs mt-0.5" : ""}>{children}</div>
        {code && (
          <div className="text-[10px] uppercase tracking-wide opacity-70 mt-1">
            code: {code}
          </div>
        )}
      </div>
      {onRetry && (
        <button
          onClick={onRetry}
          className="shrink-0 text-xs font-medium underline hover:no-underline"
        >
          Retry
        </button>
      )}
    </div>
  );
}
