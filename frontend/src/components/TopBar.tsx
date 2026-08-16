// TopBar — user/meta: profile, role badge, logout, active account id.
// No manual left margin (parent is flex column with Sidebar sibling).

import { useAuth } from "@/auth/AuthContext";
import { Chip } from "./Chip";
import { LogOut, User as UserIcon } from "lucide-react";
import { useNavigate } from "react-router-dom";

function roleTone(role: string | undefined) {
  switch (role) {
    case "owner":
      return "indigo" as const;
    case "staff":
      return "violet" as const;
    default:
      return "slate" as const;
  }
}

export function TopBar() {
  const { user, logout } = useAuth();
  const navigate = useNavigate();

  function handleLogout() {
    logout();
    navigate("/login", { replace: true });
  }

  return (
    <header className="sticky top-0 z-30 h-14 bg-white border-b border-slate-200 flex items-center justify-between px-4 shrink-0">
      <div className="min-w-0">
        <h1 className="text-sm font-semibold text-slate-900 truncate">
          TradeVision AI
        </h1>
        <p className="text-[10px] text-slate-500 truncate">
          Rule-based algorithmic trading &amp; research console
        </p>
      </div>
      <div className="flex items-center gap-3">
        {user?.default_account_id && (
          <div className="hidden md:flex items-center gap-1.5 text-xs text-slate-500">
            <span>Account</span>
            <code className="px-1.5 py-0.5 bg-slate-100 rounded font-mono text-[11px] text-slate-700">
              {user.default_account_id.slice(0, 8)}
            </code>
          </div>
        )}
        {user?.role && <Chip tone={roleTone(user.role)}>{user.role}</Chip>}
        <div className="flex items-center gap-1.5 text-sm text-slate-700">
          <div className="w-7 h-7 rounded-full bg-slate-200 flex items-center justify-center">
            <UserIcon className="w-3.5 h-3.5 text-slate-600" />
          </div>
          <span className="hidden md:inline">{user?.username || "—"}</span>
        </div>
        <button
          onClick={handleLogout}
          className="text-slate-500 hover:text-rose-600 transition-colors"
          aria-label="Log out"
          title="Log out"
        >
          <LogOut className="w-4 h-4" />
        </button>
      </div>
    </header>
  );
}
