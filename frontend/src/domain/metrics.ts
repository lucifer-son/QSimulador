import type { MetricName } from "./types";

export const MM1_METRICS: MetricName[] = ["rho", "L", "Lq", "W", "Wq", "throughput"];
export const QUEUE_METRICS: MetricName[] = [...MM1_METRICS, "p_wait", "p_block"];

export interface MetricInfo {
  label: string;
  short: string;
  kind: "fraction" | "count" | "time" | "rate";
}

export const METRIC_INFO: Record<MetricName, MetricInfo> = {
  rho: { label: "Utilização", short: "ρ", kind: "fraction" },
  L: { label: "Nº médio no sistema", short: "L", kind: "count" },
  Lq: { label: "Nº médio na fila", short: "Lq", kind: "count" },
  W: { label: "Tempo médio no sistema", short: "W", kind: "time" },
  Wq: { label: "Tempo médio de espera", short: "Wq", kind: "time" },
  throughput: { label: "Vazão", short: "Vazão", kind: "rate" },
  p_wait: { label: "Probabilidade de esperar", short: "p_wait", kind: "fraction" },
  p_block: { label: "Probabilidade de recusa", short: "p_block", kind: "fraction" },
};

const UNIT_BY_KIND: Record<MetricInfo["kind"], string> = {
  fraction: "%", count: "clientes", time: "s", rate: "req/s",
};

/** Rótulo de eixo com unidade, ex.: "Tempo médio no sistema (s)". */
export function metricAxisTitle(name: MetricName): string {
  const info = METRIC_INFO[name];
  return `${info.label} (${UNIT_BY_KIND[info.kind]})`;
}
