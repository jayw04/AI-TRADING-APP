import type { RouteObject } from "react-router-dom";
import Dashboard from "./pages/Dashboard";
import Evidence from "./pages/Evidence";
import Opportunities from "./pages/Opportunities";
import Discovery from "./pages/Discovery";
import Charts from "./pages/Charts";
import Orders from "./pages/Orders";
import Positions from "./pages/Positions";
import Strategies from "./pages/Strategies";
import Journal from "./pages/Journal";
import Agent from "./pages/Agent";
import Proposals from "./pages/Proposals";
import Settings from "./pages/Settings";
import StrategyDetailPage from "./pages/Strategies/Detail";
import OpportunityHistory from "./pages/Opportunities/History";
import AuthorWithAI from "./pages/Strategies/AuthorWithAI";
import ReviewQueue from "./pages/Proposals/ReviewQueue";
import Credentials from "./pages/Settings/Credentials";
import RiskLimits from "./pages/Settings/RiskLimits";
import Accounts from "./pages/Settings/Accounts";
import TradingProfile from "./pages/Settings/TradingProfile";
import LiveTrading from "./pages/Settings/LiveTrading";
import DataStatusPage from "./pages/MarketResearch/DataStatus";
import ResearchStrategiesPage from "./pages/MarketResearch/Strategies";
import ResultsPage from "./pages/MarketResearch/Results";

export interface NavItem {
  /** Path relative to the market's base path ("" is the market home). */
  path: string;
  label: string;
  element: RouteObject["element"];
}

/** US Equities: the existing application, now under /us. */
export const US_NAV_ITEMS: NavItem[] = [
  { path: "", label: "Dashboard", element: <Dashboard /> },
  { path: "evidence", label: "Evidence", element: <Evidence /> },
  { path: "opportunities", label: "Opportunities", element: <Opportunities /> },
  { path: "discovery", label: "Discovery", element: <Discovery /> },
  { path: "charts", label: "Charts", element: <Charts /> },
  { path: "orders", label: "Orders", element: <Orders /> },
  { path: "positions", label: "Positions", element: <Positions /> },
  { path: "strategies", label: "Strategies", element: <Strategies /> },
  { path: "journal", label: "Journal", element: <Journal /> },
  { path: "agent", label: "Agent", element: <Agent /> },
  { path: "proposals", label: "Proposals", element: <Proposals /> },
  { path: "settings", label: "Settings", element: <Settings /> },
];

export const US_EXTRA_ROUTES: { path: string; element: RouteObject["element"] }[] = [
  { path: "opportunities/history", element: <OpportunityHistory /> },
  { path: "strategies/author", element: <AuthorWithAI /> },
  { path: "strategies/:id", element: <StrategyDetailPage /> },
  { path: "proposals/review", element: <ReviewQueue /> },
  { path: "settings/credentials", element: <Credentials /> },
  { path: "settings/risk-limits", element: <RiskLimits /> },
  { path: "settings/trading-profile", element: <TradingProfile /> },
  { path: "settings/accounts", element: <Accounts /> },
  { path: "settings/live-trading", element: <LiveTrading /> },
];

/** 中国 A股: research only — data status, strategy candidates and results. No trading pages. */
export const CN_NAV_ITEMS: NavItem[] = [
  { path: "data", label: "Data status · 数据状态", element: <DataStatusPage /> },
  { path: "strategies", label: "Strategies · 策略", element: <ResearchStrategiesPage /> },
  { path: "results", label: "Results · 测试结果", element: <ResultsPage /> },
];

/** Top-level path segments of the pre-market-routing US app; old links redirect into /us. */
export const LEGACY_US_SEGMENTS: string[] = [
  ...new Set(US_NAV_ITEMS.map((i) => i.path.split("/")[0]).filter(Boolean)),
];
