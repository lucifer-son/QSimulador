import { describe, expect, it } from "vitest";
import type { ParameterSensitivity, SweepPoint } from "../api/experiments";
import { colors } from "../test/helpers";
import {
  describeServerLimits, describeUnstable, serverLines, serversChart, sweepChart, sweepSeries, tornadoChart,
  tornadoRows,
} from "./experiments";

const ok = (value: number, util: number, W: number, extra: Partial<SweepPoint> = {}): SweepPoint => ({
  value, status: "ok", message: null, offered_utilization: util, metrics: { W, rho: util }, simulation: null, ...extra,
});
const bad = (value: number, util: number, status: "unstable" | "invalid" = "unstable"): SweepPoint => ({
  value, status, message: "x", offered_utilization: util, metrics: null, simulation: null,
});

// λ de 10 a 50, μ = 40: instável a partir de 40
const points: SweepPoint[] = [
  ok(10, 0.25, 0.033), ok(20, 0.5, 0.05), ok(30, 0.75, 0.1), ok(35, 0.875, 0.2), bad(40, 1), bad(50, 1.25),
];

describe("série da varredura", () => {
  it("só inclui os pontos válidos, em ordem", () => {
    const s = sweepSeries([...points].reverse(), "W", "value");
    expect(s.x).toEqual([10, 20, 30, 35]);
    expect(s.y).toEqual([0.033, 0.05, 0.1, 0.2]);
    expect(s.omitted).toBe(2);
  });

  it("frações aparecem em %", () => {
    expect(sweepSeries(points, "rho", "value").y).toEqual([25, 50, 75, 87.5]);
  });

  it("o eixo pode ser a carga oferecida", () => {
    expect(sweepSeries(points, "W", "utilization").x).toEqual([0.25, 0.5, 0.75, 0.875]);
  });

  it("marca os pontos de alta utilização", () => {
    const s = sweepSeries(points, "W", "value");
    expect(s.high.x).toEqual([35]);
  });

  it("sombreia o trecho instável, do ponto médio até além do último ponto", () => {
    const s = sweepSeries(points, "W", "value");
    expect(s.bands).toEqual([{ x0: 37.5, x1: 50 + 5, status: "unstable" }]);
  });

  it("instabilidade no início da faixa (varredura de μ)", () => {
    const s = sweepSeries([bad(5, 2), bad(10, 1), ok(20, 0.5, 0.1)], "W", "value");
    expect(s.bands).toEqual([{ x0: 2.5, x1: 15, status: "unstable" }]);
  });

  it("trechos instável e inválido ficam em faixas separadas", () => {
    const s = sweepSeries([ok(1, 0.1, 1), bad(2, 1.2, "invalid"), bad(3, 1.5, "unstable")], "W", "value");
    expect(s.bands.map((b) => b.status)).toEqual(["invalid", "unstable"]);
  });

  it("sem pontos instáveis, não há faixas", () => {
    expect(sweepSeries(points.slice(0, 4), "W", "value").bands).toEqual([]);
  });

  it("traz a simulação com média e limites do IC", () => {
    const withSim = [ok(10, 0.25, 0.033, {
      simulation: { W: { mean: 0.034, std: 0.001, ci_low: 0.032, ci_high: 0.036, n: 5 } },
    }), ok(20, 0.5, 0.05)];
    const s = sweepSeries(withSim, "W", "value");
    expect(s.sim).toEqual({ x: [10], y: [0.034], low: [0.032], high: [0.036] });
    expect(sweepSeries(points, "W", "value").sim).toBeNull();
  });

  it("uma métrica ausente (M/M/1 não tem p_wait) não gera pontos", () => {
    expect(sweepSeries(points, "p_wait", "value").x).toEqual([]);
  });
});

describe("gráfico da varredura", () => {
  it("tem a curva analítica, a faixa instável e eixos com unidade", () => {
    const chart = sweepChart(sweepSeries(points, "W", "value"), "W", "lambda", "value", colors);
    expect(chart.data).toHaveLength(2);                    // analítico + alta utilização
    expect(chart.layout.shapes).toHaveLength(1);
    expect(chart.layout.annotations[0].text).toBe("instável");
    expect(chart.layout.xaxis.title.text).toBe("Chegadas λ (req/s)");
    expect(chart.layout.yaxis.title.text).toBe("Tempo médio no sistema (s)");
  });

  it("a simulação entra como série própria, com barras de erro assimétricas", () => {
    const withSim = [ok(10, 0.25, 0.033, {
      simulation: { W: { mean: 0.034, std: 0.001, ci_low: 0.032, ci_high: 0.037, n: 5 } },
    })];
    const chart = sweepChart(sweepSeries(withSim, "W", "value"), "W", "lambda", "value", colors);
    const sim = chart.data.find((d) => (d as { name: string }).name.startsWith("Simulação")) as {
      error_y: { array: number[]; arrayminus: number[] };
    };
    expect(sim.error_y.array[0]).toBeCloseTo(0.003);
    expect(sim.error_y.arrayminus[0]).toBeCloseTo(0.002);
  });

  it("no eixo de carga oferecida, os ticks são percentuais", () => {
    const chart = sweepChart(sweepSeries(points, "W", "utilization"), "W", "lambda", "utilization", colors);
    expect(chart.layout.xaxis.tickformat).toBe(".0%");
    expect(chart.layout.xaxis.title.text).toBe("Carga oferecida λ/(c·μ)");
  });

  it("probabilidades têm sufixo %", () => {
    const chart = sweepChart(sweepSeries(points, "rho", "value"), "rho", "lambda", "value", colors);
    expect(chart.layout.yaxis.ticksuffix).toBe("%");
  });
});

describe("aviso de instabilidade", () => {
  it("resume o trecho que ficou de fora", () => {
    expect(describeUnstable(points, "lambda"))
      .toBe("2 de 6 pontos fora do regime estável (Chegadas λ de 40 a 50); não aparecem nas curvas.");
  });
  it("sem pontos problemáticos, não há aviso", () => {
    expect(describeUnstable(points.slice(0, 4), "lambda")).toBeNull();
  });
  it("pontos inválidos são descritos como fora do domínio", () => {
    expect(describeUnstable([ok(1, 0.1, 1), bad(2, 1, "invalid")], "servers"))
      .toBe("1 de 2 pontos fora do domínio do modelo (Servidores c de 2); não aparecem nas curvas.");
  });
});

describe("comparação de servidores", () => {
  const series = [
    { servers: 1, points: [ok(5, 0.5, 0.2), bad(10, 1), bad(15, 1.5)] },
    { servers: 2, points: [ok(5, 0.25, 0.11), ok(10, 0.5, 0.12), ok(15, 0.75, 0.15)] },
  ];

  it("uma linha por c, com lacuna onde o ponto não existe", () => {
    const lines = serverLines(series, "W");
    expect(lines[0].y).toEqual([0.2, null, null]);
    expect(lines[1].y).toEqual([0.11, 0.12, 0.15]);
  });

  it("séries se distinguem por cor, símbolo e traço", () => {
    const chart = serversChart(serverLines(series, "W"), "W", colors);
    const [a, b] = chart.data;
    expect(a.name).toBe("c = 1");
    expect(a.line.color).not.toBe(b.line.color);
    expect(a.marker.symbol).not.toBe(b.marker.symbol);
    expect(a.line.dash).not.toBe(b.line.dash);
    expect(a.connectgaps).toBe(false);
  });

  it("descreve onde cada série deixa de ser estável", () => {
    expect(describeServerLimits(series)).toEqual(["c = 1: instável a partir de λ = 10 req/s."]);
  });

  it("série acima da capacidade K", () => {
    expect(describeServerLimits([{ servers: 8, points: [bad(5, 0.1, "invalid"), bad(6, 0.1, "invalid")] }]))
      .toEqual(["c = 8: não existe (a capacidade K é menor que c)."]);
  });
});

describe("sensibilidade", () => {
  const side = { value: 1, status: "ok" as const, message: null, metrics: null };
  const param = (name: ParameterSensitivity["name"], low: number | null, high: number | null, e: number | null): ParameterSensitivity => ({
    name, base_value: 1, perturbation: "percent", low: side, high: side,
    effects: { W: { low_change_pct: low, high_change_pct: high, elasticity: e } },
  });
  const params = [param("mu", 10, -8, -0.9), param("lambda", -20, 60, 3.8), param("servers", null, -30, null)];

  it("ordena do parâmetro que mais pesa para o que menos pesa", () => {
    expect(tornadoRows(params, "W").map((r) => r.name)).toEqual(["lambda", "servers", "mu"]);
  });

  it("lados que não existem (instável ou inválido) ficam nulos", () => {
    const row = tornadoRows(params, "W").find((r) => r.name === "servers")!;
    expect(row.low).toBeNull();
    expect(row.high).toBe(-30);
  });

  it("métrica ausente vira linha sem efeito, sem quebrar", () => {
    expect(tornadoRows(params, "p_block")[0]).toMatchObject({ low: null, high: null, elasticity: null });
  });

  it("o gráfico distingue os dois lados por cor e por padrão, e pula o lado nulo", () => {
    const chart = tornadoChart(tornadoRows(params, "W"), "W", colors);
    const [low, high] = chart.data;
    expect(low.marker.color).not.toBe(high.marker.color);
    expect(low.marker.pattern.shape).not.toBe(high.marker.pattern.shape);
    expect(low.y).toEqual(["Chegadas λ", "Serviço μ"]);        // servers não tem o lado "diminui"
    expect(high.y).toHaveLength(3);
    expect(chart.layout.xaxis.title.text).toBe("Variação de W (%)");
  });
});
