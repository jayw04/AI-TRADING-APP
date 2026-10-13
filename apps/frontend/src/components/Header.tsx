import { useEffect, useState } from "react";
import { authApi } from "@/api/auth";
import { useOptionalMarket } from "@/markets/MarketContext";
import { marketClock } from "@/markets/format";
import { clearSessionCaches } from "@/markets/queryClient";
import MarketSelector from "./MarketSelector";

export default function Header() {
  const market = useOptionalMarket();
  const [now, setNow] = useState(() => new Date());
  useEffect(() => {
    const t = setInterval(() => setNow(new Date()), 30_000);
    return () => clearInterval(t);
  }, []);

  async function handleLogout() {
    try {
      await authApi.logout();
    } catch {
      // Ignore: we redirect to /login regardless so a dead session still clears.
    }
    clearSessionCaches();
    window.location.assign("/login");
  }

  return (
    <header className="h-12 shrink-0 flex items-center justify-between px-4 border-b border-neutral-800 bg-neutral-950">
      <div className="text-sm text-neutral-400">Trading Workbench</div>
      <div className="flex items-center gap-4">
        <MarketSelector />
        {market && (
          <span className="text-[11px] text-neutral-500" aria-label="Market currency and time">
            {market.currencyLabel} · {market.timezone} {marketClock(market, now)}
          </span>
        )}
        <span className="text-[11px] text-neutral-500">
          {market?.researchOnly ? "Research only · no orders" : "P1 · risk-gated orders"}
        </span>
        <button
          type="button"
          onClick={handleLogout}
          className="text-xs text-neutral-400 hover:text-white"
        >
          Log out
        </button>
      </div>
    </header>
  );
}
