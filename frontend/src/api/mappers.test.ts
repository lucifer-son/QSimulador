import { describe, expect, it } from "vitest";
import {
  fromCalculate, fromCompare, fromSimulate,
  type CalculateResponse, type CompareResponse, type SimulateResponse,
} from "./mappers";
import { clone, fixtures as fx } from "../test/helpers";

const params = { lambda: 1, mu: 1 };
const as = <T,>(value: unknown) => value as T;
const names = (r: { metrics: { name: string }[] }) => r.metrics.map((m) => m.name);

describe("fromCalculate", () => {
  it("M/M/1: métricas na ordem de exibição (com P0) e servers/capacity assumidos", () => {
    const r = fromCalculate("mm1", params, as<CalculateResponse>(fx.mm1Calculate));
    expect(names(r)).toEqual(["rho", "L", "Lq", "W", "Wq", "p0"]); // o calculate do M/M/1 não traz vazão
    expect(r.metrics.find((m) => m.name === "p0")!.analytical).toBe(fx.mm1Calculate.p0);
    expect(r.metrics[0]).toEqual({ name: "rho", analytical: fx.mm1Calculate.rho });
    expect(r).toMatchObject({ action: "calculate", modelLabel: "M/M/1", servers: 1, capacity: null });
  });

  it("M/M/c/K: nove métricas, com servers e capacity vindos da resposta", () => {
    const r = fromCalculate("mmck", params, as<CalculateResponse>(fx.mmckCalculate));
    expect(names(r)).toEqual(["rho", "L", "Lq", "W", "Wq", "p0", "throughput", "p_wait", "p_block"]);
    expect(r).toMatchObject({ modelLabel: "M/M/3/6", servers: 3, capacity: 6 });
    expect(r.metrics.find((m) => m.name === "p_block")!.analytical).toBe(fx.mmckCalculate.p_block);
  });

  it("M/M/c: capacity ilimitada vira null", () => {
    expect(fromCalculate("mmc", params, as<CalculateResponse>(fx.mmcCalculate)).capacity).toBeNull();
  });
});

describe("fromSimulate", () => {
  it("normaliza resumo e réplicas", () => {
    const r = fromSimulate("mmck", params, as<SimulateResponse>(fx.mmckSimulate));
    expect(r).toMatchObject({ action: "simulate", seed: 2026, replications: 5, simulationTime: 300, warmupTime: 20, confidenceLevel: 0.95 });
    expect(names(r)).toHaveLength(9);
    const rho = r.metrics.find((m) => m.name === "rho")!;
    expect(rho.simulated).toBe(fx.mmckSimulate.summary.rho.mean);
    expect(rho.ciLow).toBe(fx.mmckSimulate.summary.rho.ci_low);
    expect(rho.analytical).toBeUndefined();
    expect(r.runs).toHaveLength(5);
    expect(r.runs![0]).toMatchObject({ index: 0, measuredCustomers: fx.mmckSimulate.runs[0].measured_customers });
    expect(r.runs![0].values.p_block).toBe(fx.mmckSimulate.runs[0].p_block);
  });

  it("M/M/1: só as métricas do modelo (7, com P0)", () => {
    const r = fromSimulate("mm1", params, as<SimulateResponse>(fx.mm1Simulate));
    expect(names(r)).toEqual(["rho", "L", "Lq", "W", "Wq", "p0", "throughput"]);
    expect(r.runs![0].values.p_wait).toBeUndefined();
  });
});

describe("fromCompare", () => {
  it("junta analítico, simulação, erro e veredito do IC", () => {
    const r = fromCompare("mmck", params, as<CompareResponse>(fx.mmckCompare));
    const m = r.metrics.find((x) => x.name === "L")!;
    expect(m).toMatchObject({
      analytical: fx.mmckCompare.metrics.L.analytical,
      simulated: fx.mmckCompare.metrics.L.simulated_mean,
      errorPct: fx.mmckCompare.metrics.L.relative_error_pct,
      withinCi: true,
    });
    expect(r.allWithinCi).toBe(fx.mmckCompare.all_within_ci);
    expect(r.maxErrorPct).toBe(fx.mmckCompare.max_relative_error_pct);
    expect(r.runs).toBeUndefined(); // o /compare não devolve as réplicas
  });

  it("preserva a ausência de IC e de veredito (caso defensivo: a API exige 2+ réplicas)", () => {
    const res = clone(fx.mmckCompare) as Record<string, any>;
    for (const m of Object.values<Record<string, unknown>>(res.metrics)) Object.assign(m, { ci_low: null, ci_high: null, within_ci: null });
    res.all_within_ci = null;
    const r = fromCompare("mmck", params, as<CompareResponse>(res));
    expect(r.allWithinCi).toBeNull();
    expect(r.metrics.every((m) => m.ciLow === null && m.withinCi === null)).toBe(true);
  });

  it("M/M/1 e M/M/c compartilham o mesmo formato normalizado", () => {
    expect(names(fromCompare("mm1", params, as<CompareResponse>(fx.mm1Compare)))).toHaveLength(7);
    const mmc = fromCompare("mmc", params, as<CompareResponse>(fx.mmcCompare));
    expect(names(mmc)).toHaveLength(9);
    expect(mmc.capacity).toBeNull();
  });

  it("repassa um veredito 'fora do IC'", () => {
    const res = clone(fx.mmckCompare);
    res.metrics.L.within_ci = false;
    res.all_within_ci = false;
    const r = fromCompare("mmck", params, as<CompareResponse>(res));
    expect(r.allWithinCi).toBe(false);
    expect(r.metrics.find((m) => m.name === "L")!.withinCi).toBe(false);
  });
});
