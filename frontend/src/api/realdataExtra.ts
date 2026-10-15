import type { AnalysisResponse, CompareBody, Level, MetricComparison } from "./realdata";
import { postForm, postJson } from "./client";

// Acréscimos da Fase 7 (backend/app/api/schemas_realdata_extra.py), no mesmo estilo de realdata.ts.

export interface SimulationBody {
  simulation_time: number; replications: number; warmup_time: number; confidence_level: number; seed?: number;
}
export interface SimulatedCompareBody extends CompareBody { simulation: SimulationBody }

export interface SimulatedMetric extends MetricComparison {
  simulated_mean?: number | null; simulated_ci_low?: number | null; simulated_ci_high?: number | null;
  simulated_error_pct?: number | null; simulation_within_observed_ci?: boolean | null;
}
export interface SimulatedLevelComparison { users: number | null; metrics: Record<string, SimulatedMetric> }
export interface SimulationUsed {
  simulation_time: number; replications: number; warmup_time: number; seed: number; confidence_level: number;
}
export interface SimulatedCompareResponse {
  notation: string; comparison: SimulatedLevelComparison[]; simulation?: SimulationUsed | null;
}

export interface LevelSuggestions {
  mu: number | null; mu_source: "menor_nivel"; think_time: number | null; think_source: "estimado" | null; base_users: number;
}
export interface LevelsImport { levels: Level[]; suggestions: LevelSuggestions; warnings: string[] }

export interface ReportBody {
  format: "markdown" | "html"; title?: string;
  analysis?: AnalysisResponse; levels_import?: LevelsImport; comparison?: SimulatedCompareResponse;
}
export interface ReportResponse { format: "markdown" | "html"; filename: string; media_type: string; content: string }

export const importLevels = (form: FormData, signal?: AbortSignal) =>
  postForm<LevelsImport>("/api/realdata/import/levels", form, signal);

export const compareSimulated = (body: SimulatedCompareBody, signal?: AbortSignal) =>
  postJson<SimulatedCompareResponse>("/api/realdata/compare-simulated", body, signal);

export const buildReport = (body: ReportBody, signal?: AbortSignal) =>
  postJson<ReportResponse>("/api/realdata/report", body, signal);
