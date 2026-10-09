import { describe, expect, it } from "vitest";
import { deviationChart, deviationData } from "./deviation";
import type { MetricRow } from "../domain/types";
import { colors } from "../test/helpers";

const row = (name: MetricRow["name"], analytical: number, simulated: number, ciLow: number | null, ciHigh: number | null): MetricRow =>
  ({ name, analytical, simulated, ciLow, ciHigh });

describe("deviationData", () => {
  it("calcula a diferença percentual da média e do IC em relação ao analítico", () => {
    const { points } = deviationData([row("L", 4, 3.96, 3.8, 4.2)]);
    expect(points).toHaveLength(1);
    expect(points[0].diff).toBeCloseTo(-1);
    expect(points[0].lo).toBeCloseTo(-5);
    expect(points[0].hi).toBeCloseTo(5);
    expect(points[0]).toMatchObject({ name: "L", label: "L", within: true });
  });

  it("'within' é falso quando o analítico está fora do IC", () => {
    const { points } = deviationData([row("L", 4, 3.5, 3.4, 3.6)]);
    expect(points[0].within).toBe(false);
    // quando o analítico está fora do IC, a barra não cruza o zero
    expect(points[0].lo > 0 || points[0].hi < 0).toBe(true);
  });

  it("a barra cruza o zero exatamente quando o analítico está dentro do IC", () => {
    for (const [sim, lo, hi] of [[3.9, 3.8, 4.1], [3.5, 3.4, 3.6], [4.2, 4.1, 4.3], [4, 4, 4.5]]) {
      const [p] = deviationData([row("L", 4, sim, lo, hi)]).points;
      expect(p.lo <= 0 && p.hi >= 0).toBe(p.within);
    }
  });

  it("omite métricas com valor analítico zero (não há diferença relativa)", () => {
    const d = deviationData([row("p_block", 0, 0, 0, 0), row("L", 4, 4, 3.9, 4.1)]);
    expect(d.omitted).toEqual(["p_block"]);
    expect(d.points.map((p) => p.name)).toEqual(["L"]);
  });

  it("ignora linhas sem IC (1 réplica) ou sem um dos lados", () => {
    const d = deviationData([row("L", 4, 4, null, null), { name: "W", simulated: 1, ciLow: 0, ciHigh: 2 }]);
    expect(d.points).toEqual([]);
    expect(d.omitted).toEqual([]);
  });
});

describe("deviationChart", () => {
  const points = deviationData([row("L", 4, 4, 3.9, 4.1), row("W", 1, 1.5, 1.4, 1.6)]).points;

  it("separa em duas séries (dentro e fora do IC), com cores diferentes", () => {
    const { data } = deviationChart(points, colors);
    expect(data).toHaveLength(2);
    expect(data.map((t) => t.name)).toEqual(["Analítico dentro do IC", "Analítico fora do IC"]);
    expect(data[0].marker.color).toBe(colors.accent);
    expect(data[1].marker.color).toBe(colors.danger);
  });

  it("a legenda está sempre presente, mesmo quando tudo está dentro do IC", () => {
    expect(deviationChart(points, colors).layout.showlegend).toBe(true);
    const allInside = deviationData([row("L", 4, 4, 3.9, 4.1)]).points;
    const chart = deviationChart(allInside, colors);
    expect(chart.layout.showlegend).toBe(true);
    expect(chart.data).toHaveLength(1);
  });

  it("dentro e fora do IC diferem por cor E por forma do marcador (não só por cor)", () => {
    const { data } = deviationChart(points, colors);
    expect(data[0].marker.symbol).toBe("circle");
    expect(data[1].marker.symbol).toBe("diamond");
    expect(data[0].marker.symbol).not.toBe(data[1].marker.symbol);
    expect(data[0].marker.color).not.toBe(data[1].marker.color);
  });

  it("os dois eixos têm rótulo, e o eixo X traz a unidade (%)", () => {
    const { layout } = deviationChart(points, colors);
    expect(layout.xaxis.title.text).toMatch(/\(%\)$/);
    expect(layout.yaxis.title.text).toBe("Métrica");
  });

  it("monta as barras de erro assimétricas a partir do IC", () => {
    const { data } = deviationChart(deviationData([row("L", 4, 3.96, 3.8, 4.2)]).points, colors);
    const err = data[0].error_x;
    expect(err.symmetric).toBe(false);
    expect(err.array[0]).toBeCloseTo(6);       // hi - diff = 5 - (-1)
    expect(err.arrayminus[0]).toBeCloseTo(4);  // diff - lo = -1 - (-5)
  });

  it("o eixo é simétrico e cobre o IC; separadores em pt-BR", () => {
    const { layout } = deviationChart(deviationData([row("L", 4, 3.96, 3.8, 4.2)]).points, colors);
    expect(layout.xaxis.range[0]).toBe(-layout.xaxis.range[1]);
    expect(layout.xaxis.range[1]).toBeGreaterThan(5);
    expect(layout.separators).toBe(",.");
    expect(layout.yaxis.autorange).toBe("reversed");
  });

  it("a altura cresce com o número de métricas", () => {
    expect(deviationChart(points, colors).layout.height).toBe(120 + 30 * 2);
  });
});
