import { apiFetch } from "./client";

export interface BenchmarkRow {
  symbol: string;
  name: string;
  inception_date: string | null;
  inception_price: string | null;
  current_price: string | null;
  as_of?: string | null;
  return_pct: number | null;
}

export const benchmarksApi = {
  list(): Promise<{ items: BenchmarkRow[] }> {
    return apiFetch<{ items: BenchmarkRow[] }>("/api/v1/benchmarks");
  },
};
