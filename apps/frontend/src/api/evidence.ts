import { apiFetch } from "./client";

export interface ConfidenceComponent {
  verifiability: number;
  safety: number;
  maturity: number;
  operational: number;
}

export interface Confidence {
  score: number;
  band: string;
  components: ConfidenceComponent;
  weights: ConfidenceComponent;
  rationale: string[];
}

export interface KpiRow {
  key: string;
  label: string;
  value: number | null;
  unit: string;
  target: number;
  status: "ok" | "watch" | "n_a";
  note: string;
}

export interface ResearchProgram {
  id: string;
  family: string;
  philosophy: string;
  status: "validated" | "rejected" | "inconclusive" | "research" | "planned";
  color: "green" | "red" | "amber" | "blue" | "gray";
  headline: string;
  evidence_doc: string | null;
}

export interface StrategyBook {
  id: number;
  name: string;
  status: string;
  vol_target: number | null;
  vol_scaling: boolean;
}

export interface EvidenceSummary {
  as_of: string;
  confidence: Confidence;
  kpis: { rows: KpiRow[]; summary: Record<string, number> };
  research_programs: ResearchProgram[];
  research_status_counts: Record<string, number>;
  strategies: StrategyBook[];
}

export const evidenceApi = {
  summary(): Promise<EvidenceSummary> {
    return apiFetch<EvidenceSummary>("/api/v1/evidence/summary");
  },
};
