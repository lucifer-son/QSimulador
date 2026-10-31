import { describe, expect, it } from "vitest";
import type { CompareResult, SweepResult, TrafficResult, VideoValidation } from "../api/traffic";
import { colors, fixtures as fx } from "../test/helpers";
import {
  approachColor, planDelayChart, queueSeriesChart, sweepChart, validationDeparturesChart, validationQueueChart,
} from "./traffic";

type Ev = { type: string; result?: unknown };
const done = <R,>(events: unknown) => (events as Ev[]).find((e) => e.type === "done")!.result as R;
const traces = (c: { data: object[] }) => c.data as Record<string, any>[];

describe("gráficos do cruzamento", () => {
  const sim = fx.trafficSimulate as unknown as TrafficResult;

  it("fila: média e faixa do IC de cada aproximação, em minutos, com nomes e estilos diferentes", () => {
    const chart = queueSeriesChart(sim.series!, { a1: "Agamenon", a2: "Transversal" }, colors);
    const t = traces(chart);
    expect(t).toHaveLength(6);
    expect(t.filter((x) => x.name).map((x) => x.name)).toEqual(["Agamenon", "Transversal"]);
    expect(t[2].x[1]).toBeCloseTo(sim.series!.times[1] / 60, 10);
    expect(t[2].line.dash).toBe("solid");
    expect(t[5].line.dash).toBe("dash");              // não depende só da cor
    expect(t[1].fill).toBe("tonexty");
    expect(t[0].y).toEqual(sim.series!.a1.ci_high);
    expect(approachColor(colors, "a1")).toBe(colors.accent);
    expect(approachColor(colors, "a2")).not.toBe(colors.accent);
  });

  it("planos: uma barra por plano, com o IC como barra de erro assimétrica", () => {
    const result = done<CompareResult>(fx.trafficCompare);
    const [bar] = traces(planDelayChart(result, colors));
    expect(bar.x).toEqual(["Referência", "Mais verde na 1", "Mais verde na 2"]);
    expect(bar.y).toHaveLength(3);
    const base = result.base.metrics.x.delay_censored.simulation!;
    expect(bar.error_y.array[0]).toBeCloseTo(base.ci_high! - base.mean, 10);
    expect(bar.error_y.arrayminus[0]).toBeCloseTo(base.mean - base.ci_low!, 10);
    expect(bar.marker.color[0]).toBe(colors.textMuted);   // a referência fica em cinza
  });

  it("varredura: curva com IC, referência analítica e o ponto de menor atraso", () => {
    const result = done<SweepResult>(fx.trafficSweep);
    const t = traces(sweepChart(result, colors));
    expect(t).toHaveLength(3);
    expect(t[0].x).toEqual(result.points.map((p) => p.green[0]));
    expect(t[1].y).toEqual(result.points.map((p) => p.reference_delay));
    const best = result.points[result.best_index];
    expect(t[2].x).toEqual([best.green[0]]);
    expect(t[2].y).toEqual([best.intersection.delay_censored!.mean]);
    expect(Math.min(...t[0].y)).toBe(t[2].y[0]);
  });

  it("validação: faixa simulada, média e os pontos observados por intervalo", () => {
    const v = fx.trafficVideoValidate as unknown as VideoValidation;
    const a = v.approaches.a1;
    const q = traces(validationQueueChart(a, "A", "#378ADD", colors));
    expect(q.map((x) => x.name).filter(Boolean)).toEqual(["Faixa simulada", "Simulado (média)", "Observado"]);
    expect(q[3].mode).toBe("markers");
    expect(q[3].y).toEqual(a.intervals.map((i) => i.queue.observed));
    expect(q[3].x[0]).toBeCloseTo(a.intervals[0].end / 60, 10);
    const d = traces(validationDeparturesChart(a, "A", "#378ADD", colors));
    expect(d[3].y).toEqual(a.intervals.map((i) => i.departures.observed));
  });

  it("todos usam as cores do tema e eixos com título", () => {
    const layout = queueSeriesChart(sim.series!, { a1: "A", a2: "B" }, colors).layout as Record<string, any>;
    expect(layout.xaxis.title.text).toMatch(/Tempo/);
    expect(layout.yaxis.title.text).toMatch(/Fila/);
    expect(layout.xaxis.color).toBe(colors.textSecondary);
    expect(layout.yaxis.rangemode).toBe("tozero");
  });
});
