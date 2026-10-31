import { ApiError, apiErrorFrom, fetchApi, send } from "./client";

/**
 * Cruzamento semaforizado (Fase 13.1). Tempos em segundos e taxas em veículos por segundo, como na API.
 * Os tipos abaixo descrevem o que a tela usa; o contrato completo está em /docs da API.
 */

export interface Summary { mean: number; std?: number | null; ci_low?: number | null; ci_high?: number | null; n: number }
export type MetricMap = Record<string, Summary | null>;
export type ApproachKey = "a1" | "a2";
export type Scope = "x" | ApproachKey;

export interface TrafficAlert {
  code: string; level: string; approach?: ApproachKey | null; field?: string | null; message: string;
}
export interface TrafficSettings {
  simulation_time: number; warmup_time: number; replications: number; seed: number; confidence_level: number;
  series_step: number; diff_confidence_level?: number;
}
export interface Phase { green: number; amber: number; all_red: number }
export interface HeadwayInfo { distribution: string; label: string; mean: number; cv: number; std: number }
export interface ApproachInfo {
  key: ApproachKey; name: string; saturation: number; capacity: number; effective_green: number; arrival_rate: number;
  headway: HeadwayInfo; first_vehicle_time: number; amber_usable: number; initial_queue: number;
  not_informed: string[]; profile_blocks: number;
}
export interface ApproachReference {
  kind: "webster" | "fluid"; exact: boolean; saturation: number; capacity: number; arrival_rate: number;
  uniform_delay: number; delay: number; delay_censored: number; queue_end: number | null; queue_mean: number;
}
export interface WebsterCycle { exact: boolean; cycle: number; critical_ratio_sum: number; lost_time: number }
export interface TrafficReference {
  a1: ApproachReference; a2: ApproachReference; delay: number | null; delay_censored: number | null;
  webster_cycle: WebsterCycle | null;
}
export interface Band { mean: number[]; ci_low: number[]; ci_high: number[] }
export interface QueueSeries { times: number[]; a1: Band; a2: Band }

export interface TrafficResult {
  settings: TrafficSettings;
  plan: { phases: Phase[]; cycle: number; offset: number; offset_informed: boolean };
  approaches: ApproachInfo[];
  alerts: TrafficAlert[];
  metrics: Record<Scope, MetricMap>;
  reference: TrafficReference;
  series: QueueSeries | null;
}

// ---------- comparação de planos ----------

export type Verdict = "higher" | "lower" | "inconclusive";
export interface CompareMetric {
  simulation: Summary | null; better: "lower" | "higher" | null; diff: Summary | null;
  relative_change: number | null; verdict: Verdict | null;
}
export interface PlanRow {
  index: number; role: "base" | "plan"; name: string; status: "ok" | "error"; message: string | null;
  phases: Phase[]; cycle: number; saturation: Record<ApproachKey, number>; alerts: TrafficAlert[];
  reference: TrafficReference; metrics: Record<Scope, Record<string, CompareMetric>> | Record<string, never>;
  series?: QueueSeries | null;
}
export interface MultipleComparisonNote { correction: string; comparisons: number; confidence_level: number; note: string }
export interface CompareResult {
  settings: TrafficSettings; multiple_comparison: MultipleComparisonNote; base: PlanRow; plans: PlanRow[];
}

// ---------- varredura do verde ----------

export type SweepVerdict = "best" | "worse" | "better" | "indistinguishable" | "unknown";
export interface SweepPoint {
  index: number; green: [number, number]; saturation: Record<ApproachKey, number>;
  intersection: MetricMap; a1: MetricMap; a2: MetricMap; reference_delay: number | null;
  vs_best: { verdict: SweepVerdict; diff: Summary | null };
}
export interface SweepResult {
  settings: TrafficSettings; cycle: number; green_total: number; best_index: number; points: SweepPoint[];
  webster_cycle: WebsterCycle | null; note: string;
}

export interface TrafficEvent {
  type: "start" | "base" | "plan" | "point" | "done" | "error";
  total?: number; completed?: number; code?: string; message?: string; field?: string;
  settings?: TrafficSettings; multiple_comparison?: MultipleComparisonNote; cycle?: number; green_total?: number;
  plan?: PlanRow; point?: SweepPoint; result?: CompareResult | SweepResult;
}

// ---------- dados do vídeo ----------

export interface SuggestedApproach {
  name: string; profile: { duration: number; lambda: number }[];
  headway: { distribution: string; mean: number; cv?: number; k?: number } | null;
  first_vehicle_time: number | null; amber_usable: number | null; initial_queue: number | null;
}
export interface SuggestedBody {
  phases: { green: number | null; amber: number | null; all_red: number | null }[]; offset: number;
  approaches: SuggestedApproach[]; simulation_time: number;
}
export interface Stat { mean: number; std?: number | null; min?: number; max?: number; n: number }
export interface VideoWarning { code: string; level: string; message: string }
export interface DischargeEstimate {
  approach_id: string; saturated_cycles: number; crossings_in_red: number; notes: string[];
  first_vehicle_time: (Stat & { ci_low: number; ci_high: number; first_crossing_mean: number }) | null;
  headway: { n: number; mean: number; ci_low: number; ci_high: number; std: number; cv: number; suggestion: SuggestedApproach["headway"] } | null;
  amber_usable: { value: number; n: number; pressured_cycles: number } | null;
}
export interface VideoEstimate {
  session_id: string | null; horizon: number; approach_ids: string[];
  method: { max_headway: number; min_run: number; core: number; profile_block: number; confidence_level: number; note: string };
  signal: {
    phases: SuggestedBody["phases"]; offset: number; offset_source: string; cycle: Stat; warnings: VideoWarning[];
  };
  arrivals: Record<ApproachKey, {
    approach_id: string; mean_rate: number; mean_rate_ci: [number, number]; arrivals: number; initial_queue: number | null;
    blocks: { start: number; duration: number; arrivals: number; lam: number; ci_low: number; ci_high: number }[];
  }>;
  discharge: Record<ApproachKey, DischargeEstimate> | null;
  suggested: SuggestedBody;
  notes: string[];
}

export interface ValidationErrors { n: number; bias: number; mae: number; rmse: number; coverage: number }
export interface ValidationInterval {
  start: number; end: number;
  queue: { observed: number | null; mean: number; low: number; high: number };
  departures: { observed: number | null; mean: number; low: number; high: number };
}
export interface ValidationApproach {
  approach_id: string; intervals: ValidationInterval[]; queue: ValidationErrors | null; departures: ValidationErrors | null;
  departures_total: { observed: number | null; mean: number; low: number; high: number; relative_error: number | null };
  excluded: { queue: number; departures: number };
  delay: {
    observed_mean: number; observed_ci: [number, number]; observed_n: number; simulated_mean: number;
    simulated_low: number; simulated_high: number; note: string;
  } | null;
}
export interface VideoValidation {
  approaches: Record<ApproachKey, ValidationApproach>;
  settings: { simulation_time: number; replications: number; seed: number; band_level: number; note: string };
  notes: string[];
}

// ---------- chamadas ----------

const JSON_POST = (body: unknown): RequestInit => ({
  method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body),
});

export function simulateTraffic(body: unknown, signal?: AbortSignal): Promise<TrafficResult> {
  return send<TrafficResult>("/api/traffic/simulate", JSON_POST(body), signal);
}

/**
 * POST em /api/traffic/compare ou /api/traffic/sweep: lê o NDJSON e chama `onEvent` a cada linha completa.
 * Cancelar o `signal` fecha a conexão, e o servidor interrompe o que falta. Um evento `error` no meio do
 * fluxo vira ApiError, como os 422 que vêm antes do fluxo.
 */
export async function streamTraffic(
  path: "/api/traffic/compare" | "/api/traffic/sweep", body: unknown, onEvent: (event: TrafficEvent) => void,
  signal?: AbortSignal,
): Promise<void> {
  const response = await fetchApi(path, JSON_POST(body), signal);
  if (!response.ok) throw await apiErrorFrom(response);
  if (!response.body) throw new ApiError("http", "A API não enviou o fluxo de resultados.");

  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let pending = "";
  const flush = (line: string) => {
    if (!line.trim()) return;
    const event = JSON.parse(line) as TrafficEvent;
    if (event.type === "error") {
      const code = event.code === "insufficient_sample" ? "insufficient_sample" : "http";
      throw new ApiError(code, event.message ?? "Falha na simulação do cruzamento.");
    }
    onEvent(event);
  };
  try {
    for (;;) {
      const { done, value } = await reader.read();
      if (done) break;
      pending += decoder.decode(value, { stream: true });
      const lines = pending.split("\n");
      pending = lines.pop() ?? "";
      lines.forEach(flush);
    }
    pending += decoder.decode();
    flush(pending);
  } catch (error) {
    if (error instanceof ApiError) throw error;
    const aborted = signal?.aborted || (error instanceof DOMException && error.name === "AbortError");
    if (aborted) throw new ApiError("aborted", "Execução cancelada.");
    throw new ApiError("network", "A conexão com a API foi interrompida.");
  }
}

export type TrafficCsvPath = "/api/traffic/export.csv" | "/api/traffic/compare/export.csv" | "/api/traffic/sweep/export.csv";

/** Refaz o cálculo com o mesmo corpo e a mesma semente e devolve o CSV. */
export async function exportTrafficCsv(path: TrafficCsvPath, body: unknown, signal?: AbortSignal): Promise<Blob> {
  const response = await fetchApi(path, JSON_POST(body), signal);
  if (!response.ok) throw await apiErrorFrom(response);
  return response.blob();
}

export function estimateVideo(form: FormData, signal?: AbortSignal): Promise<VideoEstimate> {
  return send<VideoEstimate>("/api/traffic/video/estimate", { method: "POST", body: form }, signal);
}

export function validateVideo(form: FormData, signal?: AbortSignal): Promise<VideoValidation> {
  return send<VideoValidation>("/api/traffic/video/validate", { method: "POST", body: form }, signal);
}
