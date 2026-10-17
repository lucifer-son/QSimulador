/** Modelos markovianos (serviço exponencial): os únicos com experimentos e dados reais. */
export type MarkovModelKey = "mm1" | "mmc" | "mm1k" | "mmck";
/** `mg1` é o serviço geral (M/G/1; M/D/1 quando a distribuição é determinística). */
export type ModelKey = MarkovModelKey | "mg1";

export type DistributionKey =
  | "deterministic" | "exponential" | "erlang" | "lognormal" | "weibull"
  | "uniform" | "triangular" | "truncated_normal";
/** Campos de parâmetros das distribuições de serviço (mesmos nomes da API, exceto min/max). */
export type ServiceParam = "mean" | "k" | "cv" | "min" | "mode" | "max" | "loc" | "scale";
export type Action = "compare" | "simulate" | "calculate";
export type MetricName =
  | "rho" | "L" | "Lq" | "W" | "Wq" | "p0" | "throughput" | "p_wait" | "p_block";

export type FieldKey =
  | "lambda" | "mu" | "servers" | "capacity" | "distribution" | ServiceParam
  | "simulationTime" | "replications" | "warmupTime" | "seed";
export type FormValues = Record<FieldKey, string>;
export type FieldErrors = Partial<Record<FieldKey, string>>;

export const SERVICE_FIELDS: FieldKey[] = ["distribution", "mean", "k", "cv", "min", "mode", "max", "loc", "scale"];
export const SYSTEM_FIELDS: FieldKey[] = ["lambda", "mu", "servers", "capacity", ...SERVICE_FIELDS];
/** Campos que pertencem ao sistema (cada modelo guarda os seus), em oposição aos da simulação. */
export type SystemFieldKey = "lambda" | "mu" | "servers" | "capacity" | "distribution" | ServiceParam;
export const SIM_FIELDS: FieldKey[] = ["simulationTime", "replications", "warmupTime", "seed"];

/** Parâmetros já convertidos para número (o que vai para a API). */
export interface Params {
  lambda: number;
  mu: number;
  servers?: number;
  capacity?: number;
  simulationTime?: number;
  replications?: number;
  warmupTime?: number;
  seed?: number;
  /** Só no M/G/1: distribuição de serviço e os números informados (para reabrir do histórico). */
  service?: ServiceParams;
}

export interface ServiceParams {
  distribution: DistributionKey;
  values: Partial<Record<ServiceParam, number>>;
}

/** Descrição do serviço devolvida pela API (valores efetivos, inclusive os derivados). */
export interface ServiceInfo {
  distribution: DistributionKey;
  label: string;
  mean: number;
  std: number;
  variance: number;
  cv: number;
  mu: number;
  parameters: Record<string, number>;
}

export interface MetricRow {
  name: MetricName;
  analytical?: number;
  simulated?: number;
  std?: number | null;
  ciLow?: number | null;
  ciHigh?: number | null;
  errorPct?: number | null;
  withinCi?: boolean | null;
}

export interface RunRow {
  index: number;
  measuredCustomers: number;
  values: Partial<Record<MetricName, number>>;
}

/** Resultado normalizado, igual para os quatro modelos e as três ações. */
export interface ViewResult {
  action: Action;
  modelKey: ModelKey;
  modelLabel: string;
  servers: number;
  capacity: number | null;
  params: Params;
  seed?: number;
  replications?: number;
  simulationTime?: number;
  warmupTime?: number;
  confidenceLevel?: number;
  /** Só no M/G/1. */
  service?: ServiceInfo;
  metrics: MetricRow[];
  allWithinCi?: boolean | null;
  maxErrorPct?: number | null;
  runs?: RunRow[];
  raw: unknown;
}
