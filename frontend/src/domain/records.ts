/**
 * Histórico: como cada tela vira um registro (RF-25) e como o registro volta à tela (RF-26).
 *
 * `params` e `result` são guardados como a API/a tela os produziu. Ao reabrir, os dados
 * são conferidos antes de usar: um registro salvo por outra versão do app não pode
 * derrubar a tela.
 */
import type { ScenariosResult } from "../api/scenarios";
import type { SizingResponse } from "../api/sizing";
import type { CostUnit, SizingAction } from "./sizing";
import type { NewRecord, RecordDetail, RecordKind } from "../api/records";
import type { AnalysisResponse } from "../api/realdata";
import type { CompareResult, SweepResult, TrafficResult, VideoValidation } from "../api/traffic";
import type { FitResult } from "../api/analysis";
import type {
  ServerComparisonResponse, SensitivityResponse, ServicesComparisonResponse, SweepResponse,
} from "../api/experiments";
import { VARIABLE_INFO, type SweepVariable } from "./experiments";
import { EXPERIMENT_MODEL_ORDER, LAB_MODEL_ORDER, MODELS, usesService } from "./models";
import type { Action, ExperimentModelKey, ModelKey, Params, ViewResult } from "./types";

export const KIND_LABELS: Record<RecordKind, string> = {
  model: "Cálculo analítico",
  simulation: "Simulação",
  comparison: "Comparação",
  experiment: "Experimento",
  realdata: "Dados reais",
  traffic: "Cruzamento",
};
export const KIND_ORDER: RecordKind[] = ["model", "simulation", "comparison", "experiment", "realdata", "traffic"];

const ACTION_KIND: Record<Action, RecordKind> = { calculate: "model", simulate: "simulation", compare: "comparison" };
const ACTION_LABEL: Record<Action, string> = { calculate: "Cálculo", simulate: "Simulação", compare: "Comparação" };

const isObject = (v: unknown): v is Record<string, unknown> => typeof v === "object" && v !== null && !Array.isArray(v);
const isLabModel = (v: unknown): v is ModelKey => typeof v === "string" && (LAB_MODEL_ORDER as string[]).includes(v);
const isModel = (v: unknown): v is ExperimentModelKey => typeof v === "string" && (EXPERIMENT_MODEL_ORDER as string[]).includes(v);

// ---------- Laboratório ----------

/** O rótulo do modelo já traz c e K (ex.: "M/M/3/6"), então o título só acrescenta λ e μ. */
export function labTitle(result: ViewResult): string {
  const { lambda, mu } = result.params;
  // M/G/1: o serviço é descrito pela distribuição, e μ = 1/E[S] vem arredondado da API.
  const service = result.service
    ? `λ=${lambda}, ${result.service.label}, E[S]=${Number(result.service.mean.toPrecision(4))}`
    : `λ=${lambda}, μ=${mu}`;
  return `${result.modelLabel} · ${ACTION_LABEL[result.action]} (${service})`;
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
  if (params.origin !== "lab" || !isLabModel(params.model)) return null;
  const action = params.action;
  if (action !== "calculate" && action !== "simulate" && action !== "compare") return null;
  const parameters = params.parameters;
  if (!isObject(parameters) || typeof parameters.lambda !== "number" || typeof parameters.mu !== "number") return null;
  if (result.modelKey !== params.model || result.action !== action || !Array.isArray(result.metrics)) return null;
  if (usesService(params.model) && !isObject(parameters.service)) return null;   // sem a distribuição não há como reabrir
  return { model: params.model, action, parameters: parameters as unknown as Params, result: result as unknown as ViewResult };
}

// ---------- Experimentos ----------

export type ExperimentType = "sweep" | "servers" | "services" | "sensitivity" | "sizing" | "scenarios";

export type ExperimentSnapshot =
  | { type: "sweep"; model: ExperimentModelKey; result: SweepResponse }
  | { type: "servers"; model: ExperimentModelKey; result: ServerComparisonResponse }
  | { type: "services"; model: "mg1" | "mgc"; result: ServicesComparisonResponse }
  | { type: "sensitivity"; model: ExperimentModelKey; result: SensitivityResponse }
  | { type: "sizing"; model: ExperimentModelKey; action: SizingAction; costUnit: CostUnit; result: SizingResponse }
  | { type: "scenarios"; model: ExperimentModelKey; result: ScenariosResult };

export function experimentTitle(type: ExperimentType, model: ExperimentModelKey, result: { variable?: string }): string {
  const label = MODELS[model].label;
  if (type === "sweep") {
    const variable = VARIABLE_INFO[result.variable as SweepVariable]?.label ?? result.variable ?? "parâmetro";
    return `Varredura de ${variable} · ${label}`;
  }
  if (type === "services") return `Comparação de distribuições · ${label}`;
  if (type === "sizing") return `Dimensionamento · ${label}`;
  if (type === "scenarios") return `Cenários · ${label}`;
  return type === "servers" ? `Comparação de servidores · ${label}` : `Sensibilidade · ${label}`;
}

export function experimentRecord(
  type: ExperimentType, model: ExperimentModelKey, request: unknown, result: object, title: string,
  extra: Record<string, unknown> = {},
): NewRecord {
  return {
    kind: "experiment",
    title,
    // O dimensionamento e a comparação de cenários são experimentos dos tipos "sizing" e "scenarios"
    // (kind continua "experiment": o esquema do banco não muda).
    params: { origin: "experiment", experiment: type, model, request: request ?? null, ...extra },
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
      return Array.isArray(result.series) && model !== "mg1"
        ? { type: "servers", model, result: result as unknown as ServerComparisonResponse } : null;
    case "services":
      return Array.isArray(result.series) && (model === "mg1" || model === "mgc")
        ? { type: "services", model, result: result as unknown as ServicesComparisonResponse } : null;
    case "sensitivity":
      return Array.isArray(result.parameters) ? { type: "sensitivity", model, result: result as unknown as SensitivityResponse } : null;
    case "sizing": {
      const action = params.sizing_action;
      if (action !== "table" && action !== "sla" && action !== "cost") return null;
      if (!Array.isArray(result.rows)) return null;
      const costUnit: CostUnit = params.cost_unit === "s" || params.cost_unit === "min" ? params.cost_unit : "h";
      return { type: "sizing", model, action, costUnit, result: result as unknown as SizingResponse };
    }
    case "scenarios":
      return isObject(result.base) && Array.isArray(result.scenarios) && isObject(result.settings)
        ? { type: "scenarios", model, result: result as unknown as ScenariosResult } : null;
    default:
      return null;
  }
}

// ---------- Ajuste de distribuição (Fase 13) ----------

/** O ajuste é um experimento do tipo "fit" (kind continua "experiment": o esquema do banco não muda). */
export function fitTitle(result: FitResult): string {
  const best = result.candidates.find((c) => c.key === result.best);
  return `Ajuste de distribuição · n = ${result.n.toLocaleString("pt-BR")}${best ? ` (melhor AIC: ${best.label})` : ""}`;
}

export function fitRecord(request: Record<string, unknown>, result: FitResult, title: string = fitTitle(result)): NewRecord {
  // A amostra inteira vai em `result`? Não: só o resumo, para o registro caber no limite. A semente reproduz o p-valor.
  const { sample: _sample, ...settings } = request;
  return {
    kind: "experiment",
    title,
    params: { origin: "experiment", experiment: "fit", request: { ...settings, n: result.n, seed: result.seed } },
    result: result as unknown as Record<string, unknown>,
  };
}

export function parseFitRecord(record: RecordDetail): FitResult | null {
  const { params, result } = record;
  if (params.origin !== "experiment" || params.experiment !== "fit") return null;
  return Array.isArray(result.candidates) && isObject(result.histogram) && isObject(result.suggestion)
    ? (result as unknown as FitResult) : null;
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


// ---------- Cruzamento semaforizado (Fase 13.1) ----------

export type TrafficSnapshot =
  | { type: "simulate"; result: TrafficResult }
  | { type: "compare"; result: CompareResult }
  | { type: "sweep"; result: SweepResult }
  | { type: "validation"; result: VideoValidation };

export const TRAFFIC_TITLE: Record<TrafficSnapshot["type"], string> = {
  simulate: "Simulação do cruzamento", compare: "Planos semafóricos", sweep: "Varredura do verde", validation: "Validação com o vídeo",
};

export function trafficRecord(type: TrafficSnapshot["type"], request: unknown, result: object, title: string = TRAFFIC_TITLE[type]): NewRecord {
  return { kind: "traffic", title, params: { origin: "traffic", mode: type, request: request ?? null }, result: result as Record<string, unknown> };
}

export function parseTrafficRecord(record: RecordDetail): TrafficSnapshot | null {
  const { params, result } = record;
  if (params.origin !== "traffic") return null;
  switch (params.mode) {
    case "simulate":
      return isObject(result.metrics) && isObject(result.plan) && Array.isArray(result.approaches)
        ? { type: "simulate", result: result as unknown as TrafficResult } : null;
    case "compare":
      return isObject(result.base) && Array.isArray(result.plans) && isObject(result.settings)
        ? { type: "compare", result: result as unknown as CompareResult } : null;
    case "sweep":
      return Array.isArray(result.points) && typeof result.best_index === "number"
        ? { type: "sweep", result: result as unknown as SweepResult } : null;
    case "validation":
      return isObject(result.approaches) && isObject(result.settings)
        ? { type: "validation", result: result as unknown as VideoValidation } : null;
    default:
      return null;
  }
}
