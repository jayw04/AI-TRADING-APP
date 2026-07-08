import { apiFetch } from "./client";

/** One (symbol, ET day): our avg buy/sell fill + the stock's daily low/high. Decimals arrive as strings. */
export interface RangeExecutionRow {
  et_date: string;
  symbol: string;
  avg_buy_price: string | null;
  avg_sell_price: string | null;
  daily_low: string | null;
  daily_high: string | null;
}

export interface RangeExecutionResponse {
  items: RangeExecutionRow[];
  count: number;
}

export const rangeHistoryApi = {
  /** Range Trader buy/sell vs. daily high/low over an inclusive ET date window (YYYY-MM-DD). */
  list(params: { from: string; to: string }): Promise<RangeExecutionResponse> {
    const q = new URLSearchParams({ from_date: params.from, to_date: params.to });
    return apiFetch<RangeExecutionResponse>(`/api/v1/range-execution?${q.toString()}`);
  },
};
