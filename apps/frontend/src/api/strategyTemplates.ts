import { apiFetch } from "./client";

// P8 §7 — adopt the range-trading template for a symbol (params prefilled from
// its Range Insight). Creates an IDLE strategy (authoring_method="template").

export interface ApplyRangeTemplateResult {
  id: number;
  name: string;
  status: string;
  code_path: string;
  authoring_method: string;
  symbol: string;
  prefilled_from_range_insight: boolean;
}

export const strategyTemplatesApi = {
  applyRange: (symbol: string, name?: string) =>
    apiFetch<ApplyRangeTemplateResult>("/api/v1/range-template/apply", {
      method: "POST",
      body: JSON.stringify({ symbol, name: name ?? null }),
    }),
};
