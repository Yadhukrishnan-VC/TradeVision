// DataTable — sortable headers, right-aligned numeric columns, row hover,
// empty state slot, loading skeleton rows.

import { useMemo, useState, type ReactNode } from "react";
import { ChevronDown, ChevronUp, ChevronsUpDown } from "lucide-react";
import { EmptyState } from "./EmptyState";
import { SkeletonRow } from "./Skeleton";

export interface Column<T> {
  key: string;
  header: ReactNode;
  /** Render the cell for a row. */
  cell: (row: T) => ReactNode;
  /** Right-align numeric columns. */
  numeric?: boolean;
  /** Sortable; returns a comparison key. */
  sortAccessor?: (row: T) => string | number | null | undefined;
  className?: string;
}

interface DataTableProps<T> {
  columns: Column<T>[];
  rows: T[];
  loading?: boolean;
  emptyTitle?: string;
  emptyDescription?: string;
  rowKey: (row: T, i: number) => string;
  onRowClick?: (row: T) => void;
  initialSortKey?: string;
  initialSortDir?: "asc" | "desc";
  compact?: boolean;
}

export function DataTable<T>({
  columns,
  rows,
  loading = false,
  emptyTitle = "No data",
  emptyDescription,
  rowKey,
  onRowClick,
  initialSortKey,
  initialSortDir = "asc",
  compact = false,
}: DataTableProps<T>) {
  const [sortKey, setSortKey] = useState<string | undefined>(initialSortKey);
  const [sortDir, setSortDir] = useState<"asc" | "desc">(initialSortDir);

  const sorted = useMemo(() => {
    if (!sortKey) return rows;
    const col = columns.find((c) => c.key === sortKey && c.sortAccessor);
    if (!col || !col.sortAccessor) return rows;
    const accessor = col.sortAccessor;
    const arr = [...rows];
    arr.sort((a, b) => {
      const av = accessor(a);
      const bv = accessor(b);
      if (av === null || av === undefined) return 1;
      if (bv === null || bv === undefined) return -1;
      if (typeof av === "number" && typeof bv === "number") {
        return sortDir === "asc" ? av - bv : bv - av;
      }
      const as = String(av);
      const bs = String(bv);
      return sortDir === "asc" ? as.localeCompare(bs) : bs.localeCompare(as);
    });
    return arr;
  }, [rows, sortKey, sortDir, columns]);

  function toggleSort(col: Column<T>) {
    if (!col.sortAccessor) return;
    if (sortKey === col.key) {
      setSortDir((d) => (d === "asc" ? "desc" : "asc"));
    } else {
      setSortKey(col.key);
      setSortDir("asc");
    }
  }

  if (loading) {
    return (
      <div className="overflow-x-auto tv-scrollbar">
        <table className="min-w-full text-sm">
          <thead>
            <tr className="border-b border-slate-200">
              {columns.map((c) => (
                <th
                  key={c.key}
                  className={`px-3 py-2 text-xs font-semibold text-slate-500 ${
                    c.numeric ? "text-right" : "text-left"
                  }`}
                >
                  {c.header}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {Array.from({ length: 5 }).map((_, i) => (
              <SkeletonRow key={i} cols={columns.length} />
            ))}
          </tbody>
        </table>
      </div>
    );
  }

  if (rows.length === 0) {
    return <EmptyState title={emptyTitle} description={emptyDescription} />;
  }

  return (
    <div className="overflow-x-auto tv-scrollbar">
      <table className="min-w-full text-sm">
        <thead>
          <tr className="border-b border-slate-200">
            {columns.map((c) => {
              const sortable = !!c.sortAccessor;
              const active = sortKey === c.key;
              return (
                <th
                  key={c.key}
                  className={`px-3 py-2 text-xs font-semibold text-slate-500 select-none ${
                    c.numeric ? "text-right" : "text-left"
                  } ${sortable ? "cursor-pointer hover:text-slate-700" : ""}`}
                  onClick={() => toggleSort(c)}
                  aria-sort={
                    active ? (sortDir === "asc" ? "ascending" : "descending") : "none"
                  }
                >
                  <span className={`inline-flex items-center gap-1 ${c.numeric ? "flex-row-reverse" : ""}`}>
                    {c.header}
                    {sortable &&
                      (active ? (
                        sortDir === "asc" ? (
                          <ChevronUp className="w-3 h-3" />
                        ) : (
                          <ChevronDown className="w-3 h-3" />
                        )
                      ) : (
                        <ChevronsUpDown className="w-3 h-3 opacity-40" />
                      ))}
                  </span>
                </th>
              );
            })}
          </tr>
        </thead>
        <tbody>
          {sorted.map((row, i) => (
            <tr
              key={rowKey(row, i)}
              onClick={onRowClick ? () => onRowClick(row) : undefined}
              className={`border-b border-slate-100 ${onRowClick ? "cursor-pointer hover:bg-slate-50" : ""} ${
                compact ? "h-9" : "h-11"
              }`}
            >
              {columns.map((c) => (
                <td
                  key={c.key}
                  className={`px-3 py-2 ${
                    c.numeric ? "text-right tabular-nums font-mono" : "text-left"
                  } ${c.className || ""}`}
                >
                  {c.cell(row)}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
