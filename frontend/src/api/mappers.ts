import { MODELS } from "../domain/models";
import type {
  Action, MetricName, MetricRow, ModelKey, Params, RunRow, ViewResult,
} from "../domain/types";
import type { components } from "./schema";

type S = components["schemas"];

export type CalculateResponse = S["MM1CalculateResponse"] | S["QueueCalculateResponse"];
export type SimulateResponse = S["SimulationResponse"] | S["QueueSimulationResponse"];
export type CompareResponse = S["ComparisonResponse"] | S["QueueComparisonResponse"];

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
    params,
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
    params,
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
    params,
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
