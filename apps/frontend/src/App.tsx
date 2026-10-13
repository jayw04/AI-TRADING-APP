import { useEffect, useState, type ReactNode } from "react";
import { Link, Navigate, Route, Routes, useLocation, useParams } from "react-router-dom";
import type { QueryClient } from "@tanstack/react-query";
import MarketShell from "./markets/MarketShell";
import { defaultQueryClient, trackQueryClient } from "./markets/queryClient";
import { MARKET_IDS, MARKETS, type MarketId } from "./markets/registry";
import { useGrantedMarkets, useOptionalSession } from "./markets/session";
import { CN_NAV_ITEMS, LEGACY_US_SEGMENTS, US_EXTRA_ROUTES, US_NAV_ITEMS } from "./routes";

/** Pre-market-routing US links (/orders, /strategies/12, /charts?symbol=X) keep working under /us. */
function LegacyUsRedirect() {
  const { pathname, search, hash } = useLocation();
  return <Navigate to={`/us${pathname}${search}${hash}`} replace />;
}

function NotInMarket({ market }: { market: MarketId }) {
  const { pathname } = useLocation();
  return (
    <div role="alert" className="text-sm text-neutral-300">
      <p>
        No {MARKETS[market].label} page at <span className="font-mono">{pathname}</span>.
      </p>
      <Link to={MARKETS[market].basePath} className="text-sky-400 hover:underline">
        Go to {MARKETS[market].label} home
      </Link>
    </div>
  );
}

function GrantedLinks() {
  const grants = useGrantedMarkets();
  return (
    <ul className="mt-3 space-y-1">
      {grants.map((id) => (
        <li key={id}>
          <Link to={MARKETS[id].basePath} className="text-sky-400 hover:underline">
            {MARKETS[id].label} ({MARKETS[id].basePath})
          </Link>
        </li>
      ))}
    </ul>
  );
}

function UnsupportedMarket() {
  const { segment } = useParams();
  return (
    <div className="flex min-h-screen items-center justify-center bg-neutral-950 text-neutral-200">
      <div role="alert" className="rounded-lg border border-neutral-800 bg-neutral-900 p-6 text-sm">
        <h1 className="text-base font-semibold">Unsupported market</h1>
        <p className="mt-2 text-neutral-400">
          <span className="font-mono">{segment ?? ""}</span> is not a market this application supports. No data
          has been loaded.
        </p>
        <GrantedLinks />
      </div>
    </div>
  );
}

function ForbiddenMarket({ market }: { market: MarketId }) {
  return (
    <div className="flex min-h-screen items-center justify-center bg-neutral-950 text-neutral-200">
      <div role="alert" className="rounded-lg border border-neutral-800 bg-neutral-900 p-6 text-sm">
        <h1 className="text-base font-semibold">Market not available</h1>
        <p className="mt-2 text-neutral-400">
          {MARKETS[market].label} is not enabled for this account. No data has been loaded.
        </p>
        <GrantedLinks />
      </div>
    </div>
  );
}

function NoAccess() {
  return (
    <div className="flex min-h-screen items-center justify-center bg-neutral-950 text-neutral-200">
      <div role="alert" className="rounded-lg border border-neutral-800 bg-neutral-900 p-6 text-sm">
        <h1 className="text-base font-semibold">No market access</h1>
        <p className="mt-2 text-neutral-400">This account is not enabled for any market.</p>
      </div>
    </div>
  );
}

function Home() {
  const grants = useGrantedMarkets();
  if (grants.includes("us")) return <Navigate to={MARKETS.us.basePath} replace />;
  if (grants.includes("cn")) return <Navigate to={`${MARKETS.cn.basePath}/data`} replace />;
  return <NoAccess />;
}

function MarketGuard({ market, children }: { market: MarketId; children: ReactNode }) {
  const grants = useGrantedMarkets();
  if (!grants.includes(market)) return <ForbiddenMarket market={market} />;
  return children;
}

function MarketRoutes({ makeQueryClient }: { makeQueryClient: () => QueryClient }) {
  // One cache per market for this account. Switching markets reuses that market's own cache.
  // A different account remounts this tree, and logout clears every tracked client.
  const [clients] = useState<Record<MarketId, QueryClient>>(() => ({
    us: makeQueryClient(),
    cn: makeQueryClient(),
  }));
  useEffect(() => {
    const release = MARKET_IDS.map((id) => trackQueryClient(clients[id]));
    return () => {
      for (const id of MARKET_IDS) clients[id].clear();
      for (const stop of release) stop();
    };
  }, [clients]);

  return (
    <Routes>
      <Route path="/" element={<Home />} />
      {LEGACY_US_SEGMENTS.map((seg) => (
        <Route key={seg} caseSensitive path={`/${seg}/*`} element={<LegacyUsRedirect />} />
      ))}
      <Route
        caseSensitive
        path="/us/*"
        element={
          <MarketGuard market="us">
            <MarketShell market={MARKETS.us} client={clients.us} nav={US_NAV_ITEMS}>
              <Routes>
                {US_NAV_ITEMS.map((item) =>
                  item.path === "" ? (
                    <Route key="index" index element={item.element} />
                  ) : (
                    <Route key={item.path} path={item.path} element={item.element} />
                  ),
                )}
                {US_EXTRA_ROUTES.map((r) => (
                  <Route key={r.path} path={r.path} element={r.element} />
                ))}
                <Route path="*" element={<NotInMarket market="us" />} />
              </Routes>
            </MarketShell>
          </MarketGuard>
        }
      />
      <Route
        caseSensitive
        path="/cn/*"
        element={
          <MarketGuard market="cn">
            <MarketShell market={MARKETS.cn} client={clients.cn} nav={CN_NAV_ITEMS}>
              <Routes>
                <Route index element={<Navigate to={CN_NAV_ITEMS[0].path} replace />} />
                {CN_NAV_ITEMS.map((item) => (
                  <Route key={item.path} path={item.path} element={item.element} />
                ))}
                <Route path="*" element={<NotInMarket market="cn" />} />
              </Routes>
            </MarketShell>
          </MarketGuard>
        }
      />
      <Route path="/:segment/*" element={<UnsupportedMarket />} />
    </Routes>
  );
}

export default function App({ makeQueryClient = defaultQueryClient }: { makeQueryClient?: () => QueryClient }) {
  const session = useOptionalSession();
  return <MarketRoutes key={session?.user_id ?? 0} makeQueryClient={makeQueryClient} />;
}
