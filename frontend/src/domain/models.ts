import { MGC_METRICS, MM1_METRICS, QUEUE_METRICS } from "./metrics";
import type { ExperimentModelKey, FormValues, MarkovModelKey, MetricName, ModelKey, SystemFieldKey } from "./types";

export interface ModelInfo {
  key: ModelKey;
  label: string;
  path: string;
  usesServers: boolean;
  usesCapacity: boolean;
  metrics: MetricName[];
  /** Valores iniciais de cada modelo (exemplos da documentação). */
  example: SystemExample;
}

export type SystemExample = Pick<FormValues, SystemFieldKey>;

/** Serviço inicial de todos os modelos (só o M/G/1 o usa); os valores combinam com λ = 25. */
export const DEFAULT_SERVICE = {
  distribution: "lognormal", mean: "0.02", k: "4", cv: "0.5",
  min: "0.01", mode: "0.015", max: "0.03", loc: "0.02", scale: "0.008",
} as const;

/** Modelos markovianos, na ordem de exibição. Os dados reais usam só estes. */
export const MODEL_ORDER: MarkovModelKey[] = ["mm1", "mmc", "mm1k", "mmck"];
/** Modelos com experimentos: os markovianos e o M/G/1. */
export const EXPERIMENT_MODEL_ORDER: ExperimentModelKey[] = [...MODEL_ORDER, "mg1"];
/** Modelos do Laboratório: os anteriores, o Erlang-B (perda) e o M/G/c. */
export const LAB_MODEL_ORDER: ModelKey[] = [...EXPERIMENT_MODEL_ORDER, "erlangb", "mgc"];

export const isMarkovModel = (key: ModelKey): key is MarkovModelKey => (MODEL_ORDER as string[]).includes(key);
export const isExperimentModel = (key: ModelKey): key is ExperimentModelKey =>
  (EXPERIMENT_MODEL_ORDER as string[]).includes(key);
/** Modelos cujo serviço é uma distribuição (média, CV...), e não só μ. */
export const usesService = (key: ModelKey): key is "mg1" | "mgc" => key === "mg1" || key === "mgc";

export const MODELS: Record<ModelKey, ModelInfo> = {
  mm1: {
    key: "mm1", label: "M/M/1", path: "/api/models/mm1",
    usesServers: false, usesCapacity: false, metrics: MM1_METRICS,
    example: { ...DEFAULT_SERVICE, lambda: "40", mu: "50", servers: "1", capacity: "" },
  },
  mmc: {
    key: "mmc", label: "M/M/c", path: "/api/models/mmc",
    usesServers: true, usesCapacity: false, metrics: QUEUE_METRICS,
    example: { ...DEFAULT_SERVICE, lambda: "8", mu: "1", servers: "10", capacity: "" },
  },
  mm1k: {
    key: "mm1k", label: "M/M/1/K", path: "/api/models/mm1k",
    usesServers: false, usesCapacity: true, metrics: QUEUE_METRICS,
    example: { ...DEFAULT_SERVICE, lambda: "12", mu: "10", servers: "1", capacity: "5" },
  },
  mmck: {
    key: "mmck", label: "M/M/c/K", path: "/api/models/mmck",
    usesServers: true, usesCapacity: true, metrics: QUEUE_METRICS,
    example: { ...DEFAULT_SERVICE, lambda: "25", mu: "10", servers: "3", capacity: "6" },
  },
  mg1: {
    key: "mg1", label: "M/G/1", path: "/api/models/mg1",
    usesServers: false, usesCapacity: false, metrics: MM1_METRICS,
    example: { ...DEFAULT_SERVICE, lambda: "25", mu: "", servers: "1", capacity: "" },
  },
  erlangb: {
    key: "erlangb", label: "Erlang-B (perda)", path: "/api/models/erlangb",
    usesServers: true, usesCapacity: false, metrics: QUEUE_METRICS,
    example: { ...DEFAULT_SERVICE, lambda: "20", mu: "1", servers: "15", capacity: "" },
  },
  mgc: {
    key: "mgc", label: "M/G/c", path: "/api/models/mgc",
    usesServers: true, usesCapacity: false, metrics: MGC_METRICS,
    example: { ...DEFAULT_SERVICE, mean: "0.1", cv: "1.5", lambda: "80", mu: "", servers: "10", capacity: "" },
  },
};
