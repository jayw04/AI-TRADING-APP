import { apiFetch } from "./client";
import type { OrderActionResponse, PositionListResponse } from "./types";

export const positionsApi = {
  list(): Promise<PositionListResponse> {
    return apiFetch<PositionListResponse>("/api/v1/positions");
  },

  close(symbol: string): Promise<OrderActionResponse> {
    return apiFetch<OrderActionResponse>(
      `/api/v1/positions/${encodeURIComponent(symbol)}/close`,
      { method: "POST", body: "{}" },
    );
  },
};
