import { createContext, useContext } from "react";
import type { MarketConfig } from "./registry";

const MarketContext = createContext<MarketConfig | null>(null);

export const MarketProvider = MarketContext.Provider;

/** The market of the current route group. Throws outside a market shell rather than assuming US. */
export function useMarket(): MarketConfig {
  const market = useContext(MarketContext);
  if (market === null) throw new Error("useMarket() called outside a market route group");
  return market;
}

/** Like useMarket(), but null outside a market shell (for shared components). */
export function useOptionalMarket(): MarketConfig | null {
  return useContext(MarketContext);
}
