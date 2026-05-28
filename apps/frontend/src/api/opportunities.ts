import { apiFetch } from "./client";
import type { OpportunitiesResponse } from "./types";

export const opportunitiesApi = {
  get: () => apiFetch<OpportunitiesResponse>("/api/v1/opportunities"),
};
