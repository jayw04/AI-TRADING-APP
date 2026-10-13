/**
 * The markets the frontend knows. A market id in a URL is matched exactly; anything else is an
 * unsupported market and is shown as such, never served as US data.
 */
export type MarketId = "us" | "cn";

export interface MarketConfig {
  id: MarketId;
  /** The id the backend uses in /api/v1/markets/{apiId}/... */
  apiId: "us_equity" | "cn_ashare";
  label: string;
  currency: "USD" | "CNY";
  currencyLabel: "USD" | "RMB";
  locale: string;
  timezone: string;
  basePath: string;
  researchOnly: boolean;
  /** Whether the market's views come from the market-scoped API (US keeps its existing endpoints). */
  scopedApi: boolean;
}

export const MARKETS: Record<MarketId, MarketConfig> = {
  us: {
    id: "us",
    apiId: "us_equity",
    label: "US Equities",
    currency: "USD",
    currencyLabel: "USD",
    locale: "en-US",
    timezone: "America/New_York",
    basePath: "/us",
    researchOnly: false,
    scopedApi: false,
  },
  cn: {
    id: "cn",
    apiId: "cn_ashare",
    label: "中国 A股",
    currency: "CNY",
    currencyLabel: "RMB",
    locale: "zh-CN",
    timezone: "Asia/Shanghai",
    basePath: "/cn",
    researchOnly: true,
    scopedApi: true,
  },
};

export const MARKET_IDS: MarketId[] = ["us", "cn"];

export function parseMarketId(raw: string | null | undefined): MarketId | null {
  return raw === "us" || raw === "cn" ? raw : null;
}

export class UnsupportedMarketError extends Error {
  constructor(public market: string) {
    super(`Unsupported market "${market}". Supported: ${MARKET_IDS.join(", ")}`);
  }
}
