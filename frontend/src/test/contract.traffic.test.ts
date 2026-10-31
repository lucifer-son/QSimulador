/**
 * Contrato do cruzamento semaforizado (Fase 13.1): o cliente do frontend contra a API real.
 * Só executa com VITE_API_BASE_URL apontando para uma API no ar (ver contract.test.ts).
 */
import { describe, expect, it } from "vitest";
import { ApiError } from "../api/client";
import {
  exportTrafficCsv, simulateTraffic, streamTraffic,
  type CompareResult, type SweepResult, type TrafficEvent,
} from "../api/traffic";
import { buildComparisonBody, buildSweepBody, buildTrafficBody, exampleTraffic } from "../domain/traffic";
import { fixtures } from "./helpers";

const live = Boolean(import.meta.env.VITE_API_BASE_URL);

const example = () => {
  const form = { ...exampleTraffic(), simulationTime: "900", replications: "4" };
  const built = buildTrafficBody(form);
  if (!built.ok) throw new Error("exemplo inválido");
  return { form, body: built.body };
};

describe.skipIf(!live)("contrato do cruzamento com a API real", () => {
  it("simula e devolve o formato que a tela usa (a mesma forma da fixture gravada)", async () => {
    const { body } = example();
    const r = await simulateTraffic(body);
    expect(Object.keys(r).sort()).toEqual(Object.keys(fixtures.trafficSimulate).sort());
    expect(r.approaches.map((a) => a.key)).toEqual(["a1", "a2"]);
    expect(r.metrics.x.delay_censored?.n).toBe(4);
    expect(r.reference.a1.exact).toBe(false);
    expect(r.alerts.every((a) => ["not_informed", "oversaturated", "at_risk", "check_units"].includes(a.code))).toBe(true);
  });

  it("erro de validação traz o campo no formato que a tela traduz", async () => {
    const { body } = example();
    const one = { ...body, approaches: (body.approaches as unknown[]).slice(0, 1) };
    await expect(simulateTraffic(one)).rejects.toMatchObject({ code: "invalid_parameter", fields: [{ field: "approaches" }] });
    const worse = { ...body, phases: [{ green: -1 }, { green: 20 }] };
    const error = await simulateTraffic(worse).catch((e: unknown) => e);
    expect(error).toBeInstanceOf(ApiError);
    expect((error as ApiError).fields?.[0]?.field).toBe("phases.0.green");
  });

  it("compara planos em NDJSON e fecha com o resultado completo", async () => {
    const { form } = example();
    const built = buildComparisonBody(form, [{ id: 1, name: "Mais verde na 1", green1: "36", green2: "19", amber1: "", amber2: "", allRed1: "", allRed2: "" }], false);
    if (!built.ok) throw new Error("plano inválido");
    const events: TrafficEvent[] = [];
    await streamTraffic("/api/traffic/compare", built.body, (e) => events.push(e));
    expect(events.map((e) => e.type)).toEqual(["start", "base", "plan", "done"]);
    const result = events[3].result as CompareResult;
    expect(result.plans[0].metrics.x.delay_censored.diff).not.toBeNull();
    expect(result.base.series?.times.length).toBeGreaterThan(10);
  });

  it("varre o verde e exporta o CSV da mesma varredura", async () => {
    const { form } = example();
    const built = buildSweepBody(form, { minGreen1: "10", minGreen2: "10", step: "5" });
    if (!built.ok) throw new Error("varredura inválida");
    const events: TrafficEvent[] = [];
    await streamTraffic("/api/traffic/sweep", built.body, (e) => events.push(e));
    const result = events.at(-1)!.result as SweepResult;
    expect(result.points.length).toBe(result.points.length);
    expect(result.points[result.best_index].vs_best.verdict).toBe("best");
    const blob = await exportTrafficCsv("/api/traffic/sweep/export.csv", { ...built.body, seed: result.settings.seed });
    expect((await blob.text()).split("\r\n")[0]).toContain("verde_1_s");
  });

  it("um evento de erro no meio do fluxo vira ApiError", async () => {
    const { form } = example();
    const built = buildSweepBody(form, { minGreen1: "40", minGreen2: "40", step: "5" });
    if (!built.ok) throw new Error("varredura inválida");
    await expect(streamTraffic("/api/traffic/sweep", built.body, () => undefined)).rejects.toBeInstanceOf(ApiError);
  });
});
