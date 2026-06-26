import { apiFetch } from "./client";

// P8 §5/§6 — Range Insight: descriptive daily-range statistics for a symbol.
// Mirrors apps/backend/app/api/v1/schemas/range_insight.py.

export interface MoveStats {
  mean: number;
  median: number;
  p80: number;
}

export interface Band {
  low: number;
  high: number;
}

export interface RangeInsight {
  symbol: string;
  status: "ok" | "insufficient_data";
  bars_used: number;
  low_confidence: boolean;
  as_of: string | null;
  anchor: number | null;
  anchor_source: string | null;
  last_close: number | null;
  atr20: number | null;
  atr20_pct: number | null;
  typical_move_up: MoveStats | null;
  typical_move_down: MoveStats | null;
  support: number | null;
  resistance: number | null;
  high_band: Band | null;
  low_band: Band | null;
  intraday_range: number | null;
  classification: string | null;
  efficiency_ratio: number | null;
  disclaimer: string;
}

// P8 §5a — ranked range-trading candidates (which symbol to range-trade today).
export interface RangeCandidate {
  symbol: string;
  status: string;
  atr20: number | null;
  atr20_pct: number | null;
  intraday_range: number | null;
  classification: string | null;
  last_close: number | null;
  efficiency_ratio: number | null;
  oscillation: number | null;
  suitable: boolean;
  score: number;
  rank: number;
}

export interface RangeCandidatesResponse {
  as_of: string;
  candidates: RangeCandidate[];
}

export const rangeInsightApi = {
  get: (symbol: string) =>
    apiFetch<RangeInsight>(
      `/api/v1/range-insight/${encodeURIComponent(symbol)}`,
    ),
  candidates: (symbols?: string[]) =>
    apiFetch<RangeCandidatesResponse>(
      `/api/v1/range-insight/candidates${
        symbols && symbols.length
          ? `?symbols=${encodeURIComponent(symbols.join(","))}`
          : ""
      }`,
    ),
};
