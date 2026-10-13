import { apiFetch } from "./client";
import type { MarketConfig } from "@/markets/registry";
import { UnsupportedMarketError } from "@/markets/registry";

/**
 * Market-scoped research API: /api/v1/markets/{market}/{view}. Every request names its market, every
 * cache key starts with ["market", apiId], and a response for a different market is rejected.
 */

export type ScopedView = "data-status" | "strategies" | "results";

export class MarketMismatchError extends Error {
  constructor(expected: string, got: unknown) {
    super(`Expected ${expected} data, received ${String(got)}`);
  }
}

interface MarketHeader {
  market: string;
  label: string;
  currency: string;
  currency_label: string;
  timezone: string;
  research_only: boolean;
  scope?: string;
}

export interface DatasetStatus {
  provider: string;
  dataset: string;
  sample_label: string;
  ingests: number;
  rows: number;
  last_fetch_utc: string | null;
  symbols?: number;
  first_date?: string;
  last_date?: string;
}

export interface ProviderStatus {
  source_id: string;
  name: string;
  access: string;
  storage: string;
  presentation: string;
  basis: string;
  credential: "PRESENT" | "ABSENT" | "NOT_REQUIRED";
  datasets: DatasetStatus[];
  last_update_utc: string | null;
}

export interface DataIssue {
  issue_id?: string;
  created_at_utc?: string;
  severity: "BLOCKER" | "WARNING";
  kind: string;
  provider?: string | null;
  dataset?: string | null;
  detail: string;
}

export interface CalendarStatus {
  provider: string;
  exchange: string;
  open_days: number;
  first_day: string | null;
  last_day: string | null;
  last_open_day: string | null;
}

export interface DataStatus extends MarketHeader {
  store: "PRESENT" | "NO_STORE";
  providers: ProviderStatus[];
  calendar: CalendarStatus[];
  crosscheck: {
    crosscheck_id: string;
    created_at_utc: string;
    providers: string[];
    all_explained: boolean;
    counts: Record<string, number>;
    unexplained: Record<string, number>;
    days_compared: number;
  } | null;
  issues: DataIssue[];
}

export interface StrategyCandidate {
  candidate_id: string;
  name: string;
  hypothesis: string;
  signal: string;
  lookback_days: number;
  direction: string;
  top_k: number;
  rebalance: string;
  status: string;
  run_count: number;
  last_run: { run_id: string; created_at_utc: string; sample_label: string } | null;
}

export interface Strategies extends MarketHeader {
  candidates: StrategyCandidate[];
}

export interface RunResult {
  end_equity_cny: number;
  net_return: number;
  gross_return_before_fees: number;
  fees_cny: number;
  cost_drag?: number;
  costs_cny?: Record<string, number>;
  risk?: {
    max_drawdown: number;
    volatility_annualized: number | null;
    worst_day: number | null;
    best_day: number | null;
    trading_days: number;
  };
  turnover?: number | null;
  max_drawdown: number;
  fills: number;
  refusals: Record<string, number>;
  unexecutable_delisting_exits: Record<string, { shares: number; last_close_value_cny: number }>;
}

export interface ResearchRun {
  run_id: string;
  created_at_utc: string;
  candidate_id: string;
  sample_label: string;
  labels: string[];
  market_context: Record<string, string>;
  period: { start: string; end: string } | null;
  universe: { symbols_with_data: number; eligible: number; excluded: Record<string, string> } | null;
  capital_cny: number | null;
  commission_assumption: { rate: number; minimum_cny: number } | null;
  result: RunResult;
  limitations: {
    not_modelled: string[];
    accounting: string[];
    rules: { name: string; effective_from: string; value: string; source: string; verified: string }[];
  };
}

export interface Results extends MarketHeader {
  store: string;
  runs: ResearchRun[];
}

export function marketQueryKey(market: MarketConfig, view: ScopedView) {
  return ["market", market.apiId, view] as const;
}

async function getScoped<T extends MarketHeader>(market: MarketConfig, view: ScopedView): Promise<T> {
  if (!market.scopedApi) throw new UnsupportedMarketError(market.apiId);
  const body = await apiFetch<T>(`/api/v1/markets/${market.apiId}/${view}`);
  if (body?.market !== market.apiId) throw new MarketMismatchError(market.apiId, body?.market);
  return body;
}

export const marketsApi = {
  dataStatus: (m: MarketConfig) => getScoped<DataStatus>(m, "data-status"),
  strategies: (m: MarketConfig) => getScoped<Strategies>(m, "strategies"),
  results: (m: MarketConfig) => getScoped<Results>(m, "results"),
};
