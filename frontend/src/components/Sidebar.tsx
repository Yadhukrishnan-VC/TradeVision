// Sidebar — primary nav. Collapsible w-64 ↔ w-16.
// Uses flex layout (parent AppShell provides flex container; this is shrink-0).

import { NavLink } from "react-router-dom";
import {
  Activity,
  AlertTriangle,
  BookOpen,
  ClipboardList,
  FlaskConical,
  LayoutDashboard,
  ListChecks,
  type LucideIcon,
  MemoryStick,
  PieChart,
  Radio,
  ScrollText,
  ShieldAlert,
  ShoppingCart,
  Signal,
  Sparkles,
  Wallet,
  ChevronLeft,
  ChevronRight,
} from "lucide-react";

interface NavItem {
  to: string;
  label: string;
  icon: LucideIcon;
  end?: boolean;
}

interface NavSection {
  title: string;
  items: NavItem[];
}

const SECTIONS: NavSection[] = [
  {
    title: "Dashboard",
    items: [
      { to: "/", label: "Home", icon: LayoutDashboard, end: true },
      { to: "/portfolio", label: "Portfolio", icon: PieChart },
      { to: "/portfolio/summary", label: "Portfolio Summary", icon: PieChart },
      { to: "/positions", label: "Positions", icon: Wallet },
      { to: "/orders", label: "Orders", icon: ShoppingCart },
      { to: "/trades", label: "Trades", icon: ListChecks },
      { to: "/trades/open", label: "Open Trades", icon: ListChecks },
      { to: "/trades/closed", label: "Closed Trades", icon: ListChecks },
    ],
  },
  {
    title: "Analytics & Risk",
    items: [
      { to: "/analytics", label: "Analytics", icon: Activity },
      { to: "/risk", label: "Risk Decisions", icon: ShieldAlert },
      { to: "/reconciliation", label: "Reconciliation", icon: ScrollText },
    ],
  },
  {
    title: "Research",
    items: [
      { to: "/research/backtests", label: "Backtests", icon: FlaskConical },
      { to: "/research/walk-forward", label: "Walk-Forward", icon: Activity },
      { to: "/research/edge-validation", label: "Edge Validation", icon: AlertTriangle },
      { to: "/research/cost-sensitivity", label: "Cost Sensitivity", icon: AlertTriangle },
    ],
  },
  {
    title: "Rules & Signals",
    items: [
      { to: "/rules", label: "Rule Configs", icon: ListChecks },
      { to: "/rules/executions", label: "Rule Executions", icon: Radio },
      { to: "/signals", label: "Signals", icon: Signal },
      { to: "/recommendations", label: "Recommendations", icon: Sparkles },
      { to: "/patterns", label: "Patterns", icon: MemoryStick },
    ],
  },
  {
    title: "Memory & Watchlist",
    items: [
      { to: "/memory", label: "Trader Memory", icon: MemoryStick },
      { to: "/watchlist", label: "Watchlist", icon: ListChecks },
    ],
  },
  {
    title: "System",
    items: [
      { to: "/journal", label: "Journal", icon: BookOpen },
      { to: "/audit", label: "Audit Log", icon: ScrollText },
      { to: "/risk/kill-switch", label: "Kill Switch", icon: ShieldAlert },
      { to: "/health", label: "Pipeline Health", icon: Activity },
      { to: "/system/ingestion", label: "Raw Events", icon: ClipboardList },
    ],
  },
];

export function Sidebar({
  collapsed,
  onToggle,
}: {
  collapsed: boolean;
  onToggle: () => void;
}) {
  return (
    <aside
      className={`shrink-0 h-screen border-r border-slate-200 bg-white flex flex-col transition-all ${
        collapsed ? "w-16" : "w-64"
      }`}
    >
      <div className="h-14 flex items-center justify-between px-3 border-b border-slate-200 shrink-0">
        <div className="flex items-center gap-2 min-w-0">
          <div className="w-8 h-8 rounded-md bg-indigo-600 text-white flex items-center justify-center font-bold text-sm shrink-0">
            TV
          </div>
          {!collapsed && (
            <div className="min-w-0">
              <div className="text-sm font-semibold text-slate-900 truncate">
                TradeVision
              </div>
              <div className="text-[10px] text-slate-500 truncate">Research Console</div>
            </div>
          )}
        </div>
        <button
          onClick={onToggle}
          className="text-slate-400 hover:text-slate-600 shrink-0"
          aria-label={collapsed ? "Expand sidebar" : "Collapse sidebar"}
        >
          {collapsed ? <ChevronRight className="w-4 h-4" /> : <ChevronLeft className="w-4 h-4" />}
        </button>
      </div>
      <nav className="flex-1 overflow-y-auto tv-scrollbar py-2">
        {SECTIONS.map((section) => (
          <div key={section.title} className="mb-3">
            {!collapsed && (
              <div className="px-3 py-1 text-[10px] uppercase tracking-wider text-slate-400 font-semibold">
                {section.title}
              </div>
            )}
            <ul className="space-y-0.5 px-2">
              {section.items.map((item) => (
                <li key={item.to}>
                  <NavLink
                    to={item.to}
                    end={item.end}
                    className={({ isActive }) =>
                      `flex items-center gap-2 px-2 py-1.5 rounded-md text-sm transition-colors ${
                        collapsed ? "justify-center" : ""
                      } ${
                        isActive
                          ? "bg-indigo-50 text-indigo-700 font-medium"
                          : "text-slate-600 hover:bg-slate-100 hover:text-slate-900"
                      }`
                    }
                    title={collapsed ? item.label : undefined}
                  >
                    <item.icon className="w-4 h-4 shrink-0" />
                    {!collapsed && <span className="truncate">{item.label}</span>}
                  </NavLink>
                </li>
              ))}
            </ul>
          </div>
        ))}
      </nav>
      {!collapsed && (
        <div className="px-3 py-2 border-t border-slate-200 text-[10px] text-slate-400 shrink-0">
          Research evidence rendered honestly. No fabricated results.
        </div>
      )}
    </aside>
  );
}
