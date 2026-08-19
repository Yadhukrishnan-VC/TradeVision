// Breadcrumbs — detail page navigation.

import { Link } from "react-router-dom";
import { ChevronRight } from "lucide-react";
import type { ReactNode } from "react";

export interface Crumb {
  label: ReactNode;
  to?: string;
}

export function Breadcrumbs({ items }: { items: Crumb[] }) {
  return (
    <nav aria-label="Breadcrumb" className="flex items-center gap-1 text-sm text-slate-500 mb-4 dark:text-slate-400">
      {items.map((item, i) => {
        const isLast = i === items.length - 1;
        return (
          <span key={i} className="flex items-center gap-1 min-w-0">
            {item.to && !isLast ? (
              <Link to={item.to} className="hover:text-slate-700 truncate dark:hover:text-slate-200">
                {item.label}
              </Link>
            ) : (
              <span className={isLast ? "text-slate-900 font-medium truncate dark:text-slate-100" : "truncate"}>
                {item.label}
              </span>
            )}
            {!isLast && <ChevronRight className="w-3 h-3 text-slate-500 shrink-0" />}
          </span>
        );
      })}
    </nav>
  );
}
