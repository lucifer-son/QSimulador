import { describe, expect, it } from "vitest";
import { replicationChart, replicationSeries } from "./replications";
import type { MetricRow, RunRow } from "../domain/types";
import { colors } from "../test/helpers";

const runs: RunRow[] = [0, 1, 2].map((i) => ({ index: i, measuredCustomers: 100, values: { rho: 0.7 + i / 100, L: 3 + i } }));

describe("replicationSeries", () => {
  it("frações são exibidas em % e as réplicas numeradas a partir de 1", () => {
    const s = replicationSeries(runs, { name: "rho", analytical: 0.71, simulated: 0.71 });
    expect(s.x).toEqual([1, 2, 3]);
    expect(s.y.map((v) => Math.round(v))).toEqual([70, 71, 72]);
    expect(s.mean).toBeCloseTo(71);
    expect(s.analytical).toBeCloseTo(71);
    expect(s).toMatchObject({ scale: 100, suffix: "%" });
  });

  it("contagens, tempos e taxas ficam na escala original", () => {
    const s = replicationSeries(runs, { name: "L", analytical: 4, simulated: 4.1 });
    expect(s.y).toEqual([3, 4, 5]);
    expect(s).toMatchObject({ scale: 1, suffix: "", mean: 4.1, analytical: 4 });
  });

  it("ignora réplicas sem a métrica e aceita linha sem analítico (só simular)", () => {
    const partial: RunRow[] = [...runs, { index: 3, measuredCustomers: 1, values: {} }];
    const s = replicationSeries(partial, { name: "L", simulated: 4 } as MetricRow);
    expect(s.x).toEqual([1, 2, 3]);
    expect(s.analytical).toBeUndefined();
  });
});

describe("replicationChart", () => {
  const series = replicationSeries(runs, { name: "L", analytical: 4, simulated: 4.1 });

  it("desenha as réplicas, a média simulada e o analítico", () => {
    const { data } = replicationChart(series, colors) as { data: { name: string }[] };
    expect(data.map((t) => t.name)).toEqual(["Réplicas", "Média simulada", "Analítico"]);
  });

  it("sem analítico (só simular), omite a linha do analítico", () => {
    const only = replicationSeries(runs, { name: "L", simulated: 4.1 });
    const { data } = replicationChart(only, colors) as { data: { name: string }[] };
    expect(data.map((t) => t.name)).toEqual(["Réplicas", "Média simulada"]);
  });

  it("separadores pt-BR, sufixo de % nas frações e marcas inteiras no eixo das réplicas", () => {
    const pct = replicationChart(replicationSeries(runs, { name: "rho", simulated: 0.7 }), colors).layout as Record<string, any>;
    expect(pct.separators).toBe(",.");
    expect(pct.yaxis.ticksuffix).toBe("%");
    expect(pct.xaxis.dtick).toBe(1);
  });

  it("com muitas réplicas deixa o Plotly escolher as marcas do eixo", () => {
    const many: RunRow[] = Array.from({ length: 20 }, (_, i) => ({ index: i, measuredCustomers: 1, values: { L: i } }));
    const layout = replicationChart(replicationSeries(many, { name: "L", simulated: 1 }), colors).layout as Record<string, any>;
    expect(layout.xaxis.dtick).toBeUndefined();
  });
});
