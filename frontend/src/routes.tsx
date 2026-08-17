// Route table — full page map per 05_DATA_PAGES_AND_IA.md.
// Uses React Router v6 (per decision #9). All routes are RequireAuth-guarded
// except /login. A * catch-all redirects to /.

import { lazy, Suspense } from "react";
import { Link, Navigate, Route, Routes } from "react-router-dom";
import { RequireAuth } from "@/auth/RequireAuth";
import { useAuth } from "@/auth/AuthContext";
import { AppShell } from "@/components/AppShell";
import { Spinner } from "@/components/Spinner";
import { LoginPage } from "@/pages/Login";

// Lazy-load all page modules so initial bundle stays small.
const Loading = () => (
  <div className="flex items-center justify-center py-12">
    <Spinner size="lg" />
  </div>
);

const withShell = (el: React.ReactNode) => (
  <RequireAuth>
    <AppShell>{el}</AppShell>
  </RequireAuth>
);

// Dashboard
const DashboardHome = lazy(() => import("@/pages/DashboardHome").then((m) => ({ default: m.DashboardHome })));
const Portfolio = lazy(() => import("@/pages/Portfolio").then((m) => ({ default: m.Portfolio })));
const PortfolioSummary = lazy(() => import("@/pages/PortfolioSummary").then((m) => ({ default: m.PortfolioSummary })));
const HoldingDetail = lazy(() => import("@/pages/HoldingDetail").then((m) => ({ default: m.HoldingDetail })));
const Positions = lazy(() => import("@/pages/Positions").then((m) => ({ default: m.Positions })));
const PositionDetail = lazy(() => import("@/pages/PositionDetail").then((m) => ({ default: m.PositionDetail })));
const Orders = lazy(() => import("@/pages/Orders").then((m) => ({ default: m.Orders })));
const OrderDetail = lazy(() => import("@/pages/OrderDetail").then((m) => ({ default: m.OrderDetail })));
const Trades = lazy(() => import("@/pages/Trades").then((m) => ({ default: m.Trades })));
const TradesOpen = lazy(() => import("@/pages/TradesOpen").then((m) => ({ default: m.TradesOpen })));
const TradesClosed = lazy(() => import("@/pages/TradesClosed").then((m) => ({ default: m.TradesClosed })));
const TradeExportStatus = lazy(() => import("@/pages/TradeExportStatus").then((m) => ({ default: m.TradeExportStatus })));

// Analytics & Risk
const AnalyticsPnl = lazy(() => import("@/pages/AnalyticsPnl").then((m) => ({ default: m.AnalyticsPnl })));
const AnalyticsPnlDaily = lazy(() => import("@/pages/AnalyticsPnlDaily").then((m) => ({ default: m.AnalyticsPnlDaily })));
const AnalyticsPerformance = lazy(() => import("@/pages/AnalyticsPerformance").then((m) => ({ default: m.AnalyticsPerformance })));
const AnalyticsRisk = lazy(() => import("@/pages/AnalyticsRisk").then((m) => ({ default: m.AnalyticsRisk })));

// Research
const BacktestList = lazy(() => import("@/pages/BacktestList").then((m) => ({ default: m.BacktestList })));
const BacktestDetail = lazy(() => import("@/pages/BacktestDetail").then((m) => ({ default: m.BacktestDetail })));
const WalkForward = lazy(() => import("@/pages/WalkForward").then((m) => ({ default: m.WalkForward })));
const EdgeValidation = lazy(() => import("@/pages/EdgeValidation").then((m) => ({ default: m.EdgeValidation })));
const CostSensitivity = lazy(() => import("@/pages/CostSensitivity").then((m) => ({ default: m.CostSensitivity })));
const News = lazy(() => import("@/pages/News").then((m) => ({ default: m.News })));

// Rules & Signals
const Rules = lazy(() => import("@/pages/Rules").then((m) => ({ default: m.Rules })));
const RuleDetail = lazy(() => import("@/pages/RuleDetail").then((m) => ({ default: m.RuleDetail })));
const RuleExecutions = lazy(() => import("@/pages/RuleExecutions").then((m) => ({ default: m.RuleExecutions })));
const Signals = lazy(() => import("@/pages/Signals").then((m) => ({ default: m.Signals })));
const Recommendations = lazy(() => import("@/pages/Recommendations").then((m) => ({ default: m.Recommendations })));
const Patterns = lazy(() => import("@/pages/Patterns").then((m) => ({ default: m.Patterns })));

// Memory & Watchlist
const TraderMemory = lazy(() => import("@/pages/TraderMemory").then((m) => ({ default: m.TraderMemory })));
const Watchlist = lazy(() => import("@/pages/Watchlist").then((m) => ({ default: m.Watchlist })));

// System
const Journal = lazy(() => import("@/pages/Journal").then((m) => ({ default: m.Journal })));
const Audit = lazy(() => import("@/pages/Audit").then((m) => ({ default: m.Audit })));
const KillSwitch = lazy(() => import("@/pages/KillSwitch").then((m) => ({ default: m.KillSwitch })));
const PipelineHealth = lazy(() => import("@/pages/PipelineHealth").then((m) => ({ default: m.PipelineHealth })));
const RiskDecisions = lazy(() => import("@/pages/RiskDecisions").then((m) => ({ default: m.RiskDecisions })));
const Reconciliation = lazy(() => import("@/pages/Reconciliation").then((m) => ({ default: m.Reconciliation })));
const RawIngestionEvents = lazy(() => import("@/pages/RawIngestionEvents").then((m) => ({ default: m.RawIngestionEvents })));

export function AppRoutes() {
  return (
    <Routes>
      <Route path="/login" element={<LoginPage />} />

      {/* Dashboard */}
      <Route path="/" element={withShell(<Suspense fallback={<Loading />}><DashboardHome /></Suspense>)} />
      <Route path="/portfolio" element={withShell(<Suspense fallback={<Loading />}><Portfolio /></Suspense>)} />
      <Route path="/portfolio/summary" element={withShell(<Suspense fallback={<Loading />}><PortfolioSummary /></Suspense>)} />
      <Route path="/portfolio/holdings/:symbol" element={withShell(<Suspense fallback={<Loading />}><HoldingDetail /></Suspense>)} />
      <Route path="/positions" element={withShell(<Suspense fallback={<Loading />}><Positions /></Suspense>)} />
      <Route path="/positions/:id" element={withShell(<Suspense fallback={<Loading />}><PositionDetail /></Suspense>)} />
      <Route path="/orders" element={withShell(<Suspense fallback={<Loading />}><Orders /></Suspense>)} />
      <Route path="/orders/:id" element={withShell(<Suspense fallback={<Loading />}><OrderDetail /></Suspense>)} />
      <Route path="/trades" element={withShell(<Suspense fallback={<Loading />}><Trades /></Suspense>)} />
      <Route path="/trades/open" element={withShell(<Suspense fallback={<Loading />}><TradesOpen /></Suspense>)} />
      <Route path="/trades/closed" element={withShell(<Suspense fallback={<Loading />}><TradesClosed /></Suspense>)} />
      <Route path="/trades/export/:id" element={withShell(<Suspense fallback={<Loading />}><TradeExportStatus /></Suspense>)} />

      {/* Analytics & Risk (per-account) */}
      <Route path="/analytics/:accountId/pnl" element={withShell(<Suspense fallback={<Loading />}><AnalyticsPnl /></Suspense>)} />
      <Route path="/analytics/:accountId/pnl/daily" element={withShell(<Suspense fallback={<Loading />}><AnalyticsPnlDaily /></Suspense>)} />
      <Route path="/analytics/:accountId/performance" element={withShell(<Suspense fallback={<Loading />}><AnalyticsPerformance /></Suspense>)} />
      <Route path="/analytics/:accountId/risk" element={withShell(<Suspense fallback={<Loading />}><AnalyticsRisk /></Suspense>)} />
      {/* Convenience redirect: /analytics → user's default account if known */}
      <Route path="/analytics" element={<AnalyticsIndexRedirect />} />

      {/* Research */}
      <Route path="/research/backtests" element={withShell(<Suspense fallback={<Loading />}><BacktestList /></Suspense>)} />
      <Route path="/research/backtests/:id" element={withShell(<Suspense fallback={<Loading />}><BacktestDetail /></Suspense>)} />
      <Route path="/research/walk-forward" element={withShell(<Suspense fallback={<Loading />}><WalkForward /></Suspense>)} />
      <Route path="/research/edge-validation" element={withShell(<Suspense fallback={<Loading />}><EdgeValidation /></Suspense>)} />
      <Route path="/research/cost-sensitivity" element={withShell(<Suspense fallback={<Loading />}><CostSensitivity /></Suspense>)} />
      <Route path="/news" element={withShell(<Suspense fallback={<Loading />}><News /></Suspense>)} />

      {/* Rules & Signals */}
      <Route path="/rules" element={withShell(<Suspense fallback={<Loading />}><Rules /></Suspense>)} />
      <Route path="/rules/:ruleId" element={withShell(<Suspense fallback={<Loading />}><RuleDetail /></Suspense>)} />
      <Route path="/rules/executions" element={withShell(<Suspense fallback={<Loading />}><RuleExecutions /></Suspense>)} />
      <Route path="/signals" element={withShell(<Suspense fallback={<Loading />}><Signals /></Suspense>)} />
      <Route path="/recommendations" element={withShell(<Suspense fallback={<Loading />}><Recommendations /></Suspense>)} />
      <Route path="/patterns" element={withShell(<Suspense fallback={<Loading />}><Patterns /></Suspense>)} />

      {/* Memory & Watchlist */}
      <Route path="/memory" element={withShell(<Suspense fallback={<Loading />}><TraderMemory /></Suspense>)} />
      <Route path="/watchlist" element={withShell(<Suspense fallback={<Loading />}><Watchlist /></Suspense>)} />

      {/* System */}
      <Route path="/journal" element={withShell(<Suspense fallback={<Loading />}><Journal /></Suspense>)} />
      <Route path="/journal/:correlationId" element={withShell(<Suspense fallback={<Loading />}><Journal /></Suspense>)} />
      <Route path="/audit" element={withShell(<Suspense fallback={<Loading />}><Audit /></Suspense>)} />
      <Route path="/risk" element={withShell(<Suspense fallback={<Loading />}><RiskDecisions /></Suspense>)} />
      <Route path="/risk/kill-switch" element={withShell(<Suspense fallback={<Loading />}><KillSwitch /></Suspense>)} />
      <Route path="/health" element={withShell(<Suspense fallback={<Loading />}><PipelineHealth /></Suspense>)} />
      <Route path="/reconciliation" element={withShell(<Suspense fallback={<Loading />}><Reconciliation /></Suspense>)} />
      <Route path="/system/ingestion" element={withShell(<Suspense fallback={<Loading />}><RawIngestionEvents /></Suspense>)} />

      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  );
}

function AnalyticsIndexRedirect() {
  // Per decision #3: account picker only if API exposes account list.
  // /auth/me/ may provide default_account_id. If not present, redirect home
  // with an explanatory banner.
  return <AnalyticsIndex />;
}

function AnalyticsIndex() {
  const { user } = useAuth();
  const acc = user?.default_account_id;
  if (acc) return <Navigate to={`/analytics/${acc}/pnl`} replace />;
  return (
    <RequireAuth>
      <AppShell>
        <div className="max-w-xl mx-auto py-12">
          <div className="bg-white border border-slate-200 shadow-sm rounded-lg p-6">
            <h2 className="text-lg font-semibold text-slate-900 mb-2">Analytics</h2>
            <p className="text-sm text-slate-600 mb-4">
              No default account is exposed by <code className="text-xs">/auth/me/</code>.
              Open a specific account's analytics by visiting a route like{" "}
              <code className="text-xs">/analytics/&lt;accountId&gt;/pnl</code>, or
              pick a backtest run from the{" "}
              <Link to="/research/backtests" className="text-indigo-600 underline">
                Research section
              </Link>{" "}
              to inspect that run's account.
            </p>
          </div>
        </div>
      </AppShell>
    </RequireAuth>
  );
}
