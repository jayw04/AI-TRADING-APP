import { apiFetch } from "./client";

export interface SymbolObservation {
  symbol: string;
  bias: string; // "bullish" | "bearish" | "neutral"
  key_level: number | null;
  watch_for: string;
  indicators: Record<string, unknown>;
}

export interface MorningBrief {
  user_id: number;
  brief_date: string;
  symbols: SymbolObservation[];
  overall_note: string;
  agent_used: boolean;
  trigger: string;
  generated_at: string;
}

export const morningBriefApi = {
  today: () => apiFetch<MorningBrief | null>("/api/v1/morning-brief/today"),
  generate: () =>
    apiFetch<MorningBrief>("/api/v1/morning-brief/generate", { method: "POST" }),
  recent: (limit = 7) =>
    apiFetch<MorningBrief[]>(`/api/v1/morning-brief/recent?limit=${limit}`),
};
