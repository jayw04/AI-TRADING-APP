import { apiFetch } from "./client";

// Insider Activity Monitor — Reference Only. INSIDER-001 rejected the standalone signal;
// this surface is display context under the rejected_reference_only invariant. Rows are
// sorted by filed_at DESC only (freshness) — never re-sort by value/cluster/role here.

export interface InsiderReferenceRow {
  ticker: string;
  company: string | null;
  insider_name: string | null;
  insider_role: string;
  transaction_type: string;
  transaction_date: string | null;
  filing_date: string | null;
  filed_at: string;
  transaction_value: number | null;
  open_market: boolean;
  cluster_count: number;
  pct_of_marketcap: number | null;
  pct_of_adv: number | null;
  sector: string | null;
  size_bucket: string | null;
  freshness_hours: number;
  reference_only: boolean;
}

export interface InsiderReferenceResponse {
  reference_only: boolean;
  evidence_note: string;
  evidence_doc: string;
  universe_size: number | null;
  universe_as_of: string | null;
  count: number;
  rows: InsiderReferenceRow[];
}

export const insiderReferenceApi = {
  list(windowDays = 14): Promise<InsiderReferenceResponse> {
    return apiFetch<InsiderReferenceResponse>(
      `/api/v1/insider-reference?window_days=${windowDays}`,
    );
  },
};
