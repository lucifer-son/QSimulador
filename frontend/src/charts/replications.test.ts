import { describe, expect, it } from "vitest";
import { replicationChart, replicationSeries, withAlpha } from "./replications";
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

  describe("intervalo de confiança (RF-15: analítico, média simulada e IC)", () => {
    const withCi = replicationSeries(runs, { name: "L", analytical: 4, simulated: 4.1, ciLow: 3.8, ciHigh: 4.4 });
    const traces = () =>
      (replicationChart(withCi, colors) as { data: Array<Record<string, any>> }).data;

    it("a série guarda o IC na mesma escala dos valores", () => {
      expect(withCi.ci).toEqual({ low: 3.8, high: 4.4 });
      const pct = replicationSeries(runs, { name: "rho", simulated: 0.71, ciLow: 0.7, ciHigh: 0.72 });
      expect(pct.ci!.low).toBeCloseTo(70);
      expect(pct.ci!.high).toBeCloseTo(72);
    });

    it("sem IC (1 réplica ou só calcular) não há faixa", () => {
      expect(replicationSeries(runs, { name: "L", simulated: 4, ciLow: null, ciHigh: null }).ci).toBeUndefined();
      expect(replicationSeries(runs, { name: "L", analytical: 4 }).ci).toBeUndefined();
    });

    it("desenha a faixa do IC como área preenchida, com o IC entre os limites", () => {
      const band = traces().find((t) => t.name === "Intervalo de confiança")!;
      expect(band.fill).toBe("toself");
      expect(Math.min(...band.y)).toBe(3.8);
      expect(Math.max(...band.y)).toBe(4.4);
      expect(band.fillcolor).toMatch(/^rgba\(0,0,255,0\.18\)$/);
    });

    it("séries distintas por estilo: pontos, faixa, linha tracejada e linha contínua", () => {
      const byName = Object.fromEntries(traces().map((t) => [t.name, t]));
      expect(byName["Réplicas"].mode).toBe("markers");
      expect(byName["Média simulada"].line.dash).toBe("dash");
      expect(byName["Analítico"].line.dash).toBe("solid");
      expect(byName["Média simulada"].line.dash).not.toBe(byName["Analítico"].line.dash);
    });
  });

  it("o eixo Y tem rótulo com a unidade da métrica", () => {
    const y = (name: MetricRow["name"]) =>
      (replicationChart(replicationSeries(runs, { name, simulated: 1 }), colors).layout as Record<string, any>).yaxis.title.text;
    expect(y("rho")).toBe("Utilização (%)");
    expect(y("W")).toBe("Tempo médio no sistema (s)");
    expect(y("throughput")).toBe("Vazão (req/s)");
    expect(y("L")).toBe("Nº médio no sistema (clientes)");
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

describe("withAlpha", () => {
  it("converte #rrggbb em rgba", () => expect(withAlpha("#2a6fd6", 0.5)).toBe("rgba(42,111,214,0.5)"));
  it("cor em outro formato cai num cinza neutro, sem quebrar o gráfico", () => {
    expect(withAlpha("rgb(1,2,3)", 0.2)).toBe("rgba(120,120,120,0.2)");
  });
});
