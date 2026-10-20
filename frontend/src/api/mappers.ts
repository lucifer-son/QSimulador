import { MODELS } from "../domain/models";
import type {
  Action, MetricName, MetricRow, ModelKey, Params, RunRow, ServiceInfo, ViewResult,
} from "../domain/types";
import type { components } from "./schema";

type S = components["schemas"];

export type CalculateResponse =
  | S["MM1CalculateResponse"] | S["QueueCalculateResponse"] | S["MG1CalculateResponse"]
  | S["ErlangBCalculateResponse"] | S["MGCCalculateResponse"];
export type SimulateResponse =
  | S["SimulationResponse"] | S["QueueSimulationResponse"] | S["MG1SimulationResponse"] | S["MGCSimulationResponse"];
export type CompareResponse =
  | S["ComparisonResponse"] | S["QueueComparisonResponse"] | S["MG1ComparisonResponse"] | S["MGCComparisonResponse"];

/** Só o M/G/1 devolve `service`: a descrição efetiva do tempo de serviço. */
function serviceOf(res: unknown): Pick<ViewResult, "service"> {
  const service = (res as { service?: ServiceInfo }).service;
  return service ? { service } : {};
}

/** Só o M/G/c devolve `exact` e `warnings`: se a aproximação é exata aqui e os avisos de faixa. */
function approximationOf(res: unknown): Pick<ViewResult, "approximation"> {
  const { exact, warnings } = res as { exact?: boolean; warnings?: string[] };
  return typeof exact === "boolean" ? { approximation: { exact, warnings: warnings ?? [] } } : {};
}

/** Só o cálculo do Erlang-B traz o tráfego oferecido, o carregado e as chegadas perdidas. */
function extrasOf(res: unknown): Pick<ViewResult, "extras"> {
  const r = res as Record<string, number | undefined>;
  if (r.offered_load === undefined) return {};
  return { extras: { offered_load: r.offered_load, carried_load: r.carried_load!, lost_rate: r.lost_rate! } };
}

/** No M/G/1, μ vem da API (1/E[S] efetivo); o que o formulário calculou é só uma prévia. */
function withApiMu(params: Params, res: unknown): Params {
  const service = (res as { service?: ServiceInfo }).service;
  return service ? { ...params, mu: service.mu } : params;
}

function shape(res: { servers?: number; capacity?: number | null }): { servers: number; capacity: number | null } {
  // As respostas do M/M/1 não trazem servers/capacity.
  return { servers: res.servers ?? 1, capacity: res.capacity ?? null };
}

/** Métricas do modelo, na ordem de exibição, que existem em `available`. */
function namesIn(model: ModelKey, available: Record<string, unknown>): MetricName[] {
  return MODELS[model].metrics.filter((name) => name in available);
}

export function fromCalculate(model: ModelKey, params: Params, res: CalculateResponse): ViewResult {
  const values = res as unknown as Record<string, number>;
  return {
    action: "calculate",
    modelKey: model,
    modelLabel: res.model,
    ...shape(res as { servers?: number; capacity?: number | null }),
    params: withApiMu(params, res),
    ...serviceOf(res),
    ...approximationOf(res),
    ...extrasOf(res),
    metrics: namesIn(model, values).map((name) => ({ name, analytical: values[name] })),
    raw: res,
  };
}

function toRuns(model: ModelKey, runs: SimulateResponse["runs"]): RunRow[] {
  return runs.map((run) => {
    const record = run as unknown as Record<string, number>;
    const values: RunRow["values"] = {};
    for (const name of namesIn(model, record)) values[name] = record[name];
    return { index: run.index, measuredCustomers: run.measured_customers, values };
  });
}

export function fromSimulate(model: ModelKey, params: Params, res: SimulateResponse): ViewResult {
  const metrics: MetricRow[] = namesIn(model, res.summary).map((name) => {
    const s = res.summary[name];
    return { name, simulated: s.mean, std: s.std, ciLow: s.ci_low, ciHigh: s.ci_high };
  });
  return {
    action: "simulate",
    modelKey: model,
    modelLabel: res.model,
    ...shape(res as { servers?: number; capacity?: number | null }),
    params: withApiMu(params, res),
    ...serviceOf(res),
    seed: res.seed,
    replications: res.replications,
    simulationTime: res.simulation_time,
    warmupTime: res.warmup_time,
    confidenceLevel: res.confidence_level,
    metrics,
    runs: toRuns(model, res.runs),
    raw: res,
  };
}

export function fromCompare(model: ModelKey, params: Params, res: CompareResponse): ViewResult {
  const metrics: MetricRow[] = namesIn(model, res.metrics).map((name) => {
    const m = res.metrics[name];
    return {
      name,
      analytical: m.analytical,
      simulated: m.simulated_mean,
      ciLow: m.ci_low,
      ciHigh: m.ci_high,
      errorPct: m.relative_error_pct,
      withinCi: m.within_ci,
    };
  });
  return {
    action: "compare",
    modelKey: model,
    modelLabel: res.model,
    ...shape(res as { servers?: number; capacity?: number | null }),
    params: withApiMu(params, res),
    ...serviceOf(res),
    ...approximationOf(res),
    seed: res.seed,
    replications: res.replications,
    simulationTime: res.simulation_time,
    warmupTime: res.warmup_time,
    confidenceLevel: res.confidence_level,
    metrics,
    allWithinCi: res.all_within_ci,
    maxErrorPct: res.max_relative_error_pct,
    raw: res,
  };
}

export type { Action };
