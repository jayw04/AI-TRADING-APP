import { apiFetch } from "./client";

// P8 §2/§3 — Discovery scanner. A saved boolean criterion (over supported
// indicator names) + a universe spec; runs record matched/skipped symbols.

export type UniverseKind = "discovery_feeds" | "watchlist" | "symbols";

export interface UniverseSpec {
  kind: UniverseKind;
  symbols?: string[] | null;
}

export interface ScannerDefinition {
  id: number;
  name: string;
  criteria: string;
  universe_kind: UniverseKind;
  universe_symbols: string[] | null;
  timeframe: string;
  created_at: string;
  updated_at: string;
}

export interface ScannerDefinitionInput {
  name: string;
  criteria: string;
  universe: UniverseSpec;
  timeframe?: string;
}

export interface ScannerMatchItem {
  symbol: string;
  values: Record<string, number>;
}

export interface ScannerSkipItem {
  symbol: string;
  reason: string;
}

export interface ScannerRunSummary {
  id: number;
  scanner_definition_id: number;
  run_at: string;
  status: string;
  universe_size: number;
  evaluated_count: number;
  matched_count: number;
  skipped_count: number;
  error: string | null;
}

export interface ScannerRun extends ScannerRunSummary {
  criteria_snapshot: string;
  universe_kind: string;
  timeframe: string;
  matched: ScannerMatchItem[];
  skipped: ScannerSkipItem[];
}

export interface ScannerVocabulary {
  indicators: string[];
  fields: string[];
}

export const scannerApi = {
  vocabulary: () => apiFetch<ScannerVocabulary>("/api/v1/scanner/vocabulary"),
  list: () => apiFetch<ScannerDefinition[]>("/api/v1/scanner/definitions"),
  create: (body: ScannerDefinitionInput) =>
    apiFetch<ScannerDefinition>("/api/v1/scanner/definitions", {
      method: "POST",
      body: JSON.stringify(body),
    }),
  update: (id: number, body: ScannerDefinitionInput) =>
    apiFetch<ScannerDefinition>(`/api/v1/scanner/definitions/${id}`, {
      method: "PUT",
      body: JSON.stringify(body),
    }),
  remove: (id: number) =>
    apiFetch<void>(`/api/v1/scanner/definitions/${id}`, { method: "DELETE" }),
  run: (id: number) =>
    apiFetch<ScannerRun>(`/api/v1/scanner/definitions/${id}/run`, {
      method: "POST",
    }),
  listRuns: (id: number) =>
    apiFetch<ScannerRunSummary[]>(`/api/v1/scanner/definitions/${id}/runs`),
  getRun: (runId: number) =>
    apiFetch<ScannerRun>(`/api/v1/scanner/runs/${runId}`),
};
