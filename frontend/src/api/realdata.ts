import { postForm, postJson } from "./client";

// Tipos escritos à mão a partir de backend/app/api/schemas_realdata.py. Depois de `npm run gen:api`
// (que lê o openapi.json atualizado), podem ser trocados por components["schemas"][...].

export interface Summary { mean: number | null; std?: number | null; ci_low?: number | null; ci_high?: number | null; n: number }

export interface EmpiricalMetrics {
  window_start: number; window_end: number; duration: number;
  samples: number; successes: number; rejections: number; other_failures: number;
  arrival_rate: number; throughput: number; mean_response: number;
  p50?: number | null; p90?: number | null; p95?: number | null; p99?: number | null;
  mean_in_flight: number; peak_in_flight: number;
  mean_users?: number | null; think_time?: number | null;
  p_block: number; p_error: number; arrival_cv?: number | null; response_cv?: number | null;
  summaries: Record<string, Summary>;
}

export interface Level { users: number | null; metrics: EmpiricalMetrics }

export type DiagnosticStatus = "ok" | "atencao" | "critico" | "info";
export interface Diagnostic { id: string; title: string; status: DiagnosticStatus; evidence: string }

export type Source = "informado" | "estimado";
export interface Estimates {
  mu: number | null; mu_source: "informado" | "menor_nivel" | "autoconsistente";
  servers: number; servers_source: "informado" | "estimado" | "assumido";
  think_time?: number | null; think_source?: Source | null;
  capacity?: number | null; capacity_source?: Source | null;
  notes: string[]; autoconsistent: boolean;
}

export interface ModelPick {
  key: string; notation: string; score_pct: number | null; mu: number | null; servers: number;
  capacity?: number | null; population?: number | null; think_time?: number | null;
}

export type CriterionId = "estrutura" | "capacidade" | "servidores" | "dados" | "estabilidade" | "calibracao" | "previsao";
export interface Criterion { id: CriterionId; passed: boolean; reason: string }

export interface RankingItem {
  key: string; notation: string; eligible: boolean; score_pct: number | null; scored_metrics: number;
  mu: number | null; recommended: boolean; reasons: string[];
  error_pct?: number | null; penalty_pp: number; criteria: Criterion[];
}

export interface MetricComparison {
  model: number; observed: number; observed_ci_low?: number | null; observed_ci_high?: number | null;
  absolute_error: number; relative_error_pct: number | null; model_within_observed_ci?: boolean | null;
}
export interface LevelComparison { users: number | null; metrics: Record<string, MetricComparison> }

export type Confidence = "alta" | "media" | "baixa";

export interface AnalysisResponse {
  status: "recommended" | "no_good_fit"; confidence: Confidence;
  recommended: ModelPick | null; nearest: ModelPick | null;
  ranking: RankingItem[]; rationale: string; warnings: string[]; diagnostics: Diagnostic[];
  system_type: "open" | "closed"; estimates: Estimates;
  overall: EmpiricalMetrics; levels: Level[]; comparison: LevelComparison[];
  dataset: { rows: number; rows_analyzed: number; labels: string[]; start: number; end: number };
}

export interface CompareBody {
  model: string; mu: number; servers: number; capacity?: number; think_time?: number; levels: Level[];
}
export interface CompareResponse { notation: string; comparison: LevelComparison[] }

export const analyzeCsv = (form: FormData, signal?: AbortSignal) =>
  postForm<AnalysisResponse>("/api/realdata/analyze", form, signal);

export const compareModel = (body: CompareBody, signal?: AbortSignal) =>
  postJson<CompareResponse>("/api/realdata/compare", body, signal);
