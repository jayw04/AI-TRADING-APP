import { apiFetch } from "./client";
import type { Quote } from "./types";

export const quotesApi = {
  get(symbol: string): Promise<Quote> {
    return apiFetch<Quote>(`/api/v1/quotes/${encodeURIComponent(symbol)}`);
  },
};
