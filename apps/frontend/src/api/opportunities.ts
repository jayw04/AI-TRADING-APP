import { apiFetch } from "./client";
import type { OppHistoryResponse, OpportunitiesResponse } from "./types";

export const opportunitiesApi = {
  get: () => apiFetch<OpportunitiesResponse>("/api/v1/opportunities"),
  history: (params?: { symbol?: string; family?: string }) => {
    const query = new URLSearchParams();
    if (params?.symbol) query.set("symbol", params.symbol);
    if (params?.family) query.set("family", params.family);
    const suffix = query.toString() ? `?${query.toString()}` : "";
    return apiFetch<OppHistoryResponse>(`/api/v1/opportunities/history${suffix}`);
  },
};
