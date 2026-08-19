// Skeleton — `animate-pulse` rows/cards.

export function SkeletonRow({ cols = 4 }: { cols?: number }) {
  return (
    <tr>
      {Array.from({ length: cols }).map((_, i) => (
        <td key={i} className="px-3 py-2.5">
          <div className="h-3.5 bg-slate-200 rounded animate-pulse dark:bg-slate-700" />
        </td>
      ))}
    </tr>
  );
}

export function SkeletonCard({ lines = 3 }: { lines?: number }) {
  return (
    <div className="bg-white border border-slate-200 shadow-sm rounded-lg p-4 dark:bg-slate-900 dark:border-slate-800">
      <div className="h-4 w-1/3 bg-slate-200 rounded animate-pulse mb-3 dark:bg-slate-700" />
      {Array.from({ length: lines }).map((_, i) => (
        <div
          key={i}
          className="h-3 bg-slate-100 rounded animate-pulse mb-2 dark:bg-slate-800"
          style={{ width: `${80 - i * 10}%` }}
        />
      ))}
    </div>
  );
}

export function SkeletonStat() {
  return (
    <div className="bg-white border border-slate-200 shadow-sm rounded-lg p-4 dark:bg-slate-900 dark:border-slate-800">
      <div className="h-3 w-20 bg-slate-200 rounded animate-pulse mb-2 dark:bg-slate-700" />
      <div className="h-6 w-28 bg-slate-200 rounded animate-pulse mb-2 dark:bg-slate-700" />
      <div className="h-2.5 w-16 bg-slate-100 rounded animate-pulse dark:bg-slate-800" />
    </div>
  );
}
