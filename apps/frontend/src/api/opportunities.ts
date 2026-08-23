import { apiFetch } from "./client";
import type { OppHistoryParams, OppHistoryResponse, OpportunitiesResponse } from "./types";

export const opportunitiesApi = {
  get: () => apiFetch<OpportunitiesResponse>("/api/v1/opportunities"),
  history: (params?: OppHistoryParams) => {
    const query = new URLSearchParams();
    if (params?.symbol) query.set("symbol", params.symbol);
    if (params?.family) query.set("family", params.family);
    if (params?.from_date) query.set("from_date", params.from_date);
    if (params?.to_date) query.set("to_date", params.to_date);
    if (params?.screen_version) query.set("screen_version", params.screen_version);
    if (params?.presence && params.presence !== "all") {
      query.set("presence", params.presence);
    }
    if (params?.view) query.set("view", params.view);
    const suffix = query.toString() ? `?${query.toString()}` : "";
    return apiFetch<OppHistoryResponse>(`/api/v1/opportunities/history${suffix}`);
  },
};
