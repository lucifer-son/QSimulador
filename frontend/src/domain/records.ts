/**
 * Histórico: como cada tela vira um registro (RF-25) e como o registro volta à tela (RF-26).
 *
 * `params` e `result` são guardados como a API/a tela os produziu. Ao reabrir, os dados
 * são conferidos antes de usar: um registro salvo por outra versão do app não pode
 * derrubar a tela.
 */
import type { NewRecord, RecordDetail, RecordKind } from "../api/records";
import type { AnalysisResponse } from "../api/realdata";
import type { ServerComparisonResponse, SensitivityResponse, SweepResponse } from "../api/experiments";
import { VARIABLE_INFO, type SweepVariable } from "./experiments";
import { MODEL_ORDER, MODELS } from "./models";
import type { Action, ModelKey, Params, ViewResult } from "./types";

export const KIND_LABELS: Record<RecordKind, string> = {
  model: "Cálculo analítico",
  simulation: "Simulação",
  comparison: "Comparação",
  experiment: "Experimento",
  realdata: "Dados reais",
};
export const KIND_ORDER: RecordKind[] = ["model", "simulation", "comparison", "experiment", "realdata"];

const ACTION_KIND: Record<Action, RecordKind> = { calculate: "model", simulate: "simulation", compare: "comparison" };
const ACTION_LABEL: Record<Action, string> = { calculate: "Cálculo", simulate: "Simulação", compare: "Comparação" };

const isObject = (v: unknown): v is Record<string, unknown> => typeof v === "object" && v !== null && !Array.isArray(v);
const isModel = (v: unknown): v is ModelKey => typeof v === "string" && (MODEL_ORDER as string[]).includes(v);

// ---------- Laboratório ----------

/** O rótulo do modelo já traz c e K (ex.: "M/M/3/6"), então o título só acrescenta λ e μ. */
export function labTitle(result: ViewResult): string {
  const { lambda, mu } = result.params;
  return `${result.modelLabel} · ${ACTION_LABEL[result.action]} (λ=${lambda}, μ=${mu})`;
}

export function labRecord(result: ViewResult, title: string = labTitle(result)): NewRecord {
  return {
    kind: ACTION_KIND[result.action],
    title,
    params: { origin: "lab", model: result.modelKey, action: result.action, parameters: { ...result.params } },
    result: result as unknown as Record<string, unknown>,
  };
}

export interface LabSnapshot { model: ModelKey; action: Action; parameters: Params; result: ViewResult }

export function parseLabRecord(record: RecordDetail): LabSnapshot | null {
  const { params, result } = record;
  if (params.origin !== "lab" || !isModel(params.model)) return null;
  const action = params.action;
  if (action !== "calculate" && action !== "simulate" && action !== "compare") return null;
  const parameters = params.parameters;
  if (!isObject(parameters) || typeof parameters.lambda !== "number" || typeof parameters.mu !== "number") return null;
  if (result.modelKey !== params.model || result.action !== action || !Array.isArray(result.metrics)) return null;
  return { model: params.model, action, parameters: parameters as unknown as Params, result: result as unknown as ViewResult };
}

// ---------- Experimentos ----------

export type ExperimentType = "sweep" | "servers" | "sensitivity";

export type ExperimentSnapshot =
  | { type: "sweep"; model: ModelKey; result: SweepResponse }
  | { type: "servers"; model: ModelKey; result: ServerComparisonResponse }
  | { type: "sensitivity"; model: ModelKey; result: SensitivityResponse };

export function experimentTitle(type: ExperimentType, model: ModelKey, result: { variable?: string }): string {
  const label = MODELS[model].label;
  if (type === "sweep") {
    const variable = VARIABLE_INFO[result.variable as SweepVariable]?.label ?? result.variable ?? "parâmetro";
    return `Varredura de ${variable} · ${label}`;
  }
  return type === "servers" ? `Comparação de servidores · ${label}` : `Sensibilidade · ${label}`;
}

export function experimentRecord(
  type: ExperimentType, model: ModelKey, request: unknown, result: object, title: string,
): NewRecord {
  return {
    kind: "experiment",
    title,
    params: { origin: "experiment", experiment: type, model, request: request ?? null },
    result: result as Record<string, unknown>,
  };
}

export function parseExperimentRecord(record: RecordDetail): ExperimentSnapshot | null {
  const { params, result } = record;
  if (params.origin !== "experiment" || !isModel(params.model)) return null;
  const model = params.model;
  switch (params.experiment) {
    case "sweep":
      return Array.isArray(result.points) ? { type: "sweep", model, result: result as unknown as SweepResponse } : null;
    case "servers":
      return Array.isArray(result.series) ? { type: "servers", model, result: result as unknown as ServerComparisonResponse } : null;
    case "sensitivity":
      return Array.isArray(result.parameters) ? { type: "sensitivity", model, result: result as unknown as SensitivityResponse } : null;
    default:
      return null;
  }
}

// ---------- Dados reais ----------

export function realDataTitle(result: AnalysisResponse): string {
  const pick = result.recommended ?? result.nearest;
  const rows = result.dataset.rows_analyzed.toLocaleString("pt-BR");
  return `Análise do JMeter${pick ? ` · ${pick.notation}` : ""} (${rows} amostras)`;
}

export function realDataRecord(result: AnalysisResponse, title: string = realDataTitle(result)): NewRecord {
  return {
    kind: "realdata",
    title,
    params: { origin: "realdata", source: "jtl", system_type: result.system_type },
    result: result as unknown as Record<string, unknown>,
  };
}

export function parseRealDataRecord(record: RecordDetail): AnalysisResponse | null {
  const { params, result } = record;
  if (params.origin !== "realdata" || params.source !== "jtl") return null;
  if (!isObject(result.dataset) || !Array.isArray(result.ranking) || !Array.isArray(result.levels)) return null;
  return result as unknown as AnalysisResponse;
}
