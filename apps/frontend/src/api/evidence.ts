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

/** PU-1: licence marking carried by every panel (and every KPI row). A missing field is treated as
 *  blocked (UNKNOWN) by the page; there is no way to turn the footer off. */
export type LicenseScope = "COMMERCIAL_OK" | "UNKNOWN" | "PERSONAL";

export interface PanelLicense {
  license_scope?: LicenseScope;
  license_sources?: string[];
  license_footer?: string | null;
}

export type PanelId =
  | "confidence"
  | "kpis"
  | "research_programs"
  | "research_status_counts"
  | "strategies";

export interface KpiRow extends PanelLicense {
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
  /** PU-1: combined (most restrictive) licence scope of the whole summary. A missing value is
   *  treated as UNKNOWN (blocked) by the page. Per-panel scopes are in `panels`. */
  license_scope?: LicenseScope;
  license_sources?: string[];
  license_footer?: string | null;
  panels?: Partial<Record<PanelId, PanelLicense>>;
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
