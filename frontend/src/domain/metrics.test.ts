import { describe, expect, it } from "vitest";
import { formatMetric } from "./format";
import { METRIC_INFO, MM1_METRICS, QUEUE_METRICS, metricAxisTitle } from "./metrics";
import { MODELS } from "./models";
import type { MetricName } from "./types";

describe("catálogo de métricas", () => {
  it("segue a ordem da especificação: ρ, L, Lq, W, Wq, P0; depois vazão e as probabilidades", () => {
    expect(MM1_METRICS).toEqual(["rho", "L", "Lq", "W", "Wq", "p0", "throughput"]);
    expect(QUEUE_METRICS).toEqual(["rho", "L", "Lq", "W", "Wq", "p0", "throughput", "p_wait", "p_block"]);
  });

  it("todo modelo usa uma lista que existe no catálogo", () => {
    for (const model of Object.values(MODELS)) {
      for (const name of model.metrics) expect(METRIC_INFO[name], `${model.label}/${name}`).toBeDefined();
    }
    expect(MODELS.mm1.metrics).toBe(MM1_METRICS);
    expect(MODELS.mmck.metrics).toBe(QUEUE_METRICS);
  });

  it("o P0 é uma probabilidade: aparece como porcentagem, com rótulo e símbolo próprios", () => {
    expect(METRIC_INFO.p0).toEqual({ label: "Probabilidade de sistema vazio", short: "P0", kind: "fraction" });
    expect(formatMetric("p0", 0.2)).toBe("20,0%");
    expect(formatMetric("p0", 0.2, { precise: true })).toBe("20,00%");
    expect(metricAxisTitle("p0")).toBe("Probabilidade de sistema vazio (%)");
  });

  it.each<[MetricName, string]>([
    ["rho", "Utilização (%)"], ["L", "Nº médio no sistema (clientes)"], ["Lq", "Nº médio na fila (clientes)"],
    ["W", "Tempo médio no sistema (s)"], ["Wq", "Tempo médio de espera (s)"], ["p0", "Probabilidade de sistema vazio (%)"],
    ["throughput", "Vazão (req/s)"], ["p_wait", "Probabilidade de esperar (%)"], ["p_block", "Probabilidade de recusa (%)"],
  ])("o eixo de %s tem rótulo com unidade: %s", (name, title) => {
    expect(metricAxisTitle(name)).toBe(title);
  });

  it("probabilidades são formatadas como porcentagem e tempos e taxas levam unidade", () => {
    for (const name of ["rho", "p0", "p_wait", "p_block"] as const) expect(formatMetric(name, 0.5)).toMatch(/%$/);
    expect(formatMetric("W", 0.5)).toMatch(/ s$/);
    expect(formatMetric("throughput", 5)).toMatch(/ req\/s$/);
    expect(formatMetric("L", 5)).not.toMatch(/%|s$/);
  });
});
