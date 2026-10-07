export type ModelKey = "mm1" | "mmc" | "mm1k" | "mmck";
export type Action = "compare" | "simulate" | "calculate";
export type MetricName =
  | "rho" | "L" | "Lq" | "W" | "Wq" | "throughput" | "p_wait" | "p_block";

export type FieldKey =
  | "lambda" | "mu" | "servers" | "capacity"
  | "simulationTime" | "replications" | "warmupTime" | "seed";
export type FormValues = Record<FieldKey, string>;
export type FieldErrors = Partial<Record<FieldKey, string>>;

export const SYSTEM_FIELDS: FieldKey[] = ["lambda", "mu", "servers", "capacity"];
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
  metrics: MetricRow[];
  allWithinCi?: boolean | null;
  maxErrorPct?: number | null;
  runs?: RunRow[];
  raw: unknown;
}
