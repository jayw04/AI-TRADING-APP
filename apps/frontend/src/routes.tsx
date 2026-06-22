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

export interface NavItem {
  path: string;
  label: string;
  element: RouteObject["element"];
}

export const NAV_ITEMS: NavItem[] = [
  { path: "/", label: "Dashboard", element: <Dashboard /> },
  { path: "/evidence", label: "Evidence", element: <Evidence /> },
  { path: "/opportunities", label: "Opportunities", element: <Opportunities /> },
  { path: "/discovery", label: "Discovery", element: <Discovery /> },
  { path: "/charts", label: "Charts", element: <Charts /> },
  { path: "/orders", label: "Orders", element: <Orders /> },
  { path: "/positions", label: "Positions", element: <Positions /> },
  { path: "/strategies", label: "Strategies", element: <Strategies /> },
  { path: "/journal", label: "Journal", element: <Journal /> },
  { path: "/agent", label: "Agent", element: <Agent /> },
  { path: "/proposals", label: "Proposals", element: <Proposals /> },
  { path: "/settings", label: "Settings", element: <Settings /> },
];
