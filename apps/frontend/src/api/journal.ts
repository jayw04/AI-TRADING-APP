import { apiFetch } from "./client";

/** One executed trade with its editable note (from GET /api/v1/journal). */
export interface JournalEntry {
  order_id: number;
  symbol: string;
  side: string;
  qty: string;
  avg_fill_price: string | null;
  value: string | null;
  source_type: string;
  source_id: string | null;
  source_label: string;
  filled_at: string | null;
  note: string;
}

export interface JournalListResponse {
  items: JournalEntry[];
  count: number;
}

export const journalApi = {
  list(): Promise<JournalListResponse> {
    return apiFetch<JournalListResponse>("/api/v1/journal");
  },

  saveNote(
    orderId: number,
    note: string,
  ): Promise<{ order_id: number; note: string }> {
    return apiFetch<{ order_id: number; note: string }>(
      `/api/v1/journal/${orderId}/note`,
      { method: "PUT", body: JSON.stringify({ note }) },
    );
  },
};
