import { apiFetch } from "./client";

// Each section is a free-form JSON object in §1 (structure is validated by the
// form, not the backend). The morning brief (§2) is the first reader of
// bias_thresholds.
export interface TradingProfile {
  user_id: number;
  watchlist: Record<string, unknown>;
  bias_criteria: Record<string, unknown>;
  bias_thresholds: Record<string, unknown>;
  session_preferences: Record<string, unknown>;
  risk_preferences: Record<string, unknown>;
}

// PUT accepts any subset of the five sections; omitted sections are untouched.
export type TradingProfileUpdate = Partial<Omit<TradingProfile, "user_id">>;

export const tradingProfileApi = {
  get: () => apiFetch<TradingProfile>("/api/v1/users/me/trading-profile"),
  update: (changes: TradingProfileUpdate) =>
    apiFetch<TradingProfile>("/api/v1/users/me/trading-profile", {
      method: "PUT",
      body: JSON.stringify(changes),
    }),
};
