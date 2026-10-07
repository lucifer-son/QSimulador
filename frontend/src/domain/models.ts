import { MM1_METRICS, QUEUE_METRICS } from "./metrics";
import type { MetricName, ModelKey } from "./types";

export interface ModelInfo {
  key: ModelKey;
  label: string;
  path: string;
  usesServers: boolean;
  usesCapacity: boolean;
  metrics: MetricName[];
  /** Valores iniciais de cada modelo (exemplos da documentação). */
  example: { lambda: string; mu: string; servers: string; capacity: string };
}

export const MODEL_ORDER: ModelKey[] = ["mm1", "mmc", "mm1k", "mmck"];

export const MODELS: Record<ModelKey, ModelInfo> = {
  mm1: {
    key: "mm1", label: "M/M/1", path: "/api/models/mm1",
    usesServers: false, usesCapacity: false, metrics: MM1_METRICS,
    example: { lambda: "40", mu: "50", servers: "1", capacity: "" },
  },
  mmc: {
    key: "mmc", label: "M/M/c", path: "/api/models/mmc",
    usesServers: true, usesCapacity: false, metrics: QUEUE_METRICS,
    example: { lambda: "8", mu: "1", servers: "10", capacity: "" },
  },
  mm1k: {
    key: "mm1k", label: "M/M/1/K", path: "/api/models/mm1k",
    usesServers: false, usesCapacity: true, metrics: QUEUE_METRICS,
    example: { lambda: "12", mu: "10", servers: "1", capacity: "5" },
  },
  mmck: {
    key: "mmck", label: "M/M/c/K", path: "/api/models/mmck",
    usesServers: true, usesCapacity: true, metrics: QUEUE_METRICS,
    example: { lambda: "25", mu: "10", servers: "3", capacity: "6" },
  },
};
