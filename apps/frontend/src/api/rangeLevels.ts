import { apiFetch } from "./client";

export interface RangeLevelRow {
  symbol: string;
  buy: number | null;
  sell: number | null;
  stop: number | null;
  current_price: number | null;
  position_qty: number;
  status: string;
  levels_at: string | null;
}

export interface RangeLevelsResponse {
  strategy_id: number | null;
  strategy_name: string | null;
  as_of: string;
  rows: RangeLevelRow[];
}

export const rangeLevelsApi = {
  list(strategyId?: number): Promise<RangeLevelsResponse> {
    const q = strategyId != null ? `?strategy_id=${strategyId}` : "";
    return apiFetch<RangeLevelsResponse>(`/api/v1/range-levels${q}`);
  },
};
