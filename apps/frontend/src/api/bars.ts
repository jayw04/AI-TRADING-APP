import { apiFetch } from "./client";

// OHLCV bars from the backend bar cache (GET /api/v1/bars/{symbol}).
// Prices arrive as Decimal strings; we normalize to numbers for charting.
export interface OHLCVBar {
  t: string; // ISO timestamp
  o: number;
  h: number;
  l: number;
  c: number;
  v: number;
}

export interface BarsResponse {
  symbol: string;
  timeframe: string;
  bars: OHLCVBar[];
}

interface RawBar {
  t: string;
  o: string | number;
  h: string | number;
  l: string | number;
  c: string | number;
  v: string | number;
}
interface RawBarsResponse {
  symbol: string;
  timeframe: string;
  bars: RawBar[];
}

export async function getBars(
  symbol: string,
  opts: { timeframe?: string; limit?: number } = {},
): Promise<BarsResponse> {
  const timeframe = opts.timeframe ?? "1Day";
  const limit = opts.limit ?? 120;
  const q = new URLSearchParams({ timeframe, limit: String(limit) });
  const raw = await apiFetch<RawBarsResponse>(
    `/api/v1/bars/${encodeURIComponent(symbol)}?${q.toString()}`,
  );
  return {
    symbol: raw.symbol,
    timeframe: raw.timeframe,
    bars: (raw.bars ?? []).map((b) => ({
      t: b.t,
      o: Number(b.o),
      h: Number(b.h),
      l: Number(b.l),
      c: Number(b.c),
      v: Number(b.v),
    })),
  };
}

export const barsApi = { getBars };
