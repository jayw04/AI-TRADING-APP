import type { ReactNode } from "react";
import { QueryClientProvider, type QueryClient } from "@tanstack/react-query";
import Sidebar from "@/components/Sidebar";
import Header from "@/components/Header";
import StatusBar from "@/components/StatusBar";
import ModeBanner from "@/components/ui/ModeBanner";
import type { NavItem } from "@/routes";
import { MarketProvider } from "./MarketContext";
import type { MarketConfig } from "./registry";

function ResearchBanner({ market }: { market: MarketConfig }) {
  return (
    <div
      role="status"
      aria-label="Research mode"
      className="shrink-0 bg-sky-900 px-4 py-1 text-center text-xs font-semibold tracking-wide text-sky-100"
    >
      {market.label} · RESEARCH ONLY — no broker connection, no orders, no scheduler
    </div>
  );
}

function ResearchStatusBar({ market }: { market: MarketConfig }) {
  return (
    <footer className="h-7 shrink-0 flex items-center justify-between px-3 border-t border-neutral-800 bg-neutral-950 text-[11px] text-neutral-500">
      <span>{market.label} research · separate data store</span>
      <span>
        {market.currencyLabel} · {market.timezone}
      </span>
    </footer>
  );
}

/**
 * One market's layout. Each market has its own QueryClient, so a cached response from one market can
 * never render in the other; the US shell keeps the US account banner and live status bar, the
 * research shell shows neither and offers no broker or order controls.
 */
export default function MarketShell({
  market,
  client,
  nav,
  children,
}: {
  market: MarketConfig;
  client: QueryClient;
  nav: NavItem[];
  children: ReactNode;
}) {
  return (
    <MarketProvider value={market}>
      <QueryClientProvider client={client}>
        <div className="flex flex-col h-screen bg-neutral-950 text-neutral-100" data-market={market.id}>
          {market.researchOnly ? <ResearchBanner market={market} /> : <ModeBanner />}
          <div className="flex flex-1 min-h-0">
            <Sidebar items={nav} />
            <div className="flex-1 flex flex-col min-w-0">
              <Header />
              <main className="flex-1 overflow-y-auto p-6">{children}</main>
            </div>
          </div>
          {market.researchOnly ? <ResearchStatusBar market={market} /> : <StatusBar />}
        </div>
      </QueryClientProvider>
    </MarketProvider>
  );
}
