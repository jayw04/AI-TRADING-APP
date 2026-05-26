import { apiFetch } from "./client";
import type { SignalListResponse, SignalTypeT } from "./types";

export const signalsApi = {
  list: (
    params: {
      strategy_id?: number;
      symbol?: string;
      type?: SignalTypeT;
      since?: string;
      limit?: number;
    } = {},
  ) => {
    const q = new URLSearchParams();
    if (params.strategy_id !== undefined) q.set("strategy_id", String(params.strategy_id));
    if (params.symbol) q.set("symbol", params.symbol);
    if (params.type) q.set("type", params.type);
    if (params.since) q.set("since", params.since);
    if (params.limit) q.set("limit", String(params.limit));
    const suffix = q.toString() ? `?${q}` : "";
    return apiFetch<SignalListResponse>(`/api/v1/signals${suffix}`);
  },
};
