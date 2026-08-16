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
    <nav aria-label="Breadcrumb" className="flex items-center gap-1 text-sm text-slate-500 mb-4">
      {items.map((item, i) => {
        const isLast = i === items.length - 1;
        return (
          <span key={i} className="flex items-center gap-1 min-w-0">
            {item.to && !isLast ? (
              <Link to={item.to} className="hover:text-slate-700 truncate">
                {item.label}
              </Link>
            ) : (
              <span className={isLast ? "text-slate-900 font-medium truncate" : "truncate"}>
                {item.label}
              </span>
            )}
            {!isLast && <ChevronRight className="w-3 h-3 text-slate-400 shrink-0" />}
          </span>
        );
      })}
    </nav>
  );
}
