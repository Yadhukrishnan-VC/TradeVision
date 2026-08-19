// Card — white surface, border, padding, optional header + action slot.

import type { ReactNode } from "react";

interface CardProps {
  title?: ReactNode;
  description?: ReactNode;
  actions?: ReactNode;
  children?: ReactNode;
  className?: string;
  padded?: boolean;
}

export function Card({
  title,
  description,
  actions,
  children,
  className = "",
  padded = true,
}: CardProps) {
  return (
    <section
      className={`bg-white border border-slate-200 shadow-sm rounded-lg dark:bg-slate-900 dark:border-slate-800 ${
        className ?? ""
      }`}
    >
      {(title || actions) && (
        <header className="flex items-start justify-between gap-3 px-4 py-3 border-b border-slate-100 dark:border-slate-800">
          <div className="min-w-0">
            {title && (
              <h2 className="text-sm font-semibold text-slate-900 truncate dark:text-slate-100">
                {title}
              </h2>
            )}
            {description && (
              <p className="text-xs text-slate-500 mt-0.5 truncate dark:text-slate-400">
                {description}
              </p>
            )}
          </div>
          {actions && <div className="shrink-0">{actions}</div>}
        </header>
      )}
      <div className={padded ? "p-4" : ""}>{children}</div>
    </section>
  );
}
