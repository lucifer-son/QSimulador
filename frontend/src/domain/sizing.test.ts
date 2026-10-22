import { describe, expect, it } from "vitest";
import type { SystemText } from "./experiments";
import { buildSizingBody, familyNote, INITIAL_SIZING, secondsIn, type SizingText } from "./sizing";

const mmc: SystemText = { lambda: "8", mu: "1", servers: "10", capacity: "" };
const erlang: SystemText = { lambda: "20", mu: "1", servers: "15", capacity: "" };
const mgc: SystemText = {
  lambda: "80", mu: "", servers: "10", capacity: "", distribution: "lognormal", mean: "0.1", cv: "1.5",
};
const text = (over: Partial<SizingText> = {}): SizingText => ({ ...INITIAL_SIZING, ...over });
const bodyOf = (built: ReturnType<typeof buildSizingBody>) => (built.ok ? built.body : null);

describe("corpo do dimensionamento", () => {
  it("tabela do M/M/c: sistema do Laboratório, meta em fração e custos convertidos para por segundo", () => {
    const body = bodyOf(buildSizingBody("table", "mmc", mmc, text()))!;
    expect(body).toMatchObject({ model: "mmc", lambda: 8, mu: 1, servers: 10, t: 20, target: 0.8 });
    expect(body.server_cost).toBeCloseTo(35 / 3600, 12);
    expect(body.wait_cost).toBeCloseTo(80 / 3600, 12);
    expect("c_min" in body).toBe(false);
  });
  it("a unidade dos custos define a conversão (s, min, h)", () => {
    expect(secondsIn("s")).toBe(1);
    expect(secondsIn("min")).toBe(60);
    const perMinute = bodyOf(buildSizingBody("cost", "mmc", mmc, text({ costUnit: "min", serverCost: "6" })))!;
    expect(perMinute.server_cost).toBeCloseTo(0.1, 12);
    const perSecond = bodyOf(buildSizingBody("cost", "mmc", mmc, text({ costUnit: "s", serverCost: "2" })))!;
    expect(perSecond.server_cost).toBe(2);
  });
  it("faixa de c só vai quando preenchida", () => {
    const body = bodyOf(buildSizingBody("table", "mmc", mmc, text({ cMin: "7", cMax: "12" })))!;
    expect(body).toMatchObject({ c_min: 7, c_max: 12 });
  });
  it("c não numérico vira erro no campo", () => {
    const built = buildSizingBody("table", "mmc", mmc, text({ cMin: "sete" }));
    expect(!built.ok && built.errors.cMin).toBeTruthy();
  });
  it("sem custos preenchidos, a tabela não leva custos", () => {
    const body = bodyOf(buildSizingBody("table", "mmc", mmc, text({ serverCost: "", waitCost: "" })))!;
    expect("server_cost" in body || "wait_cost" in body).toBe(false);
  });
  it("custo pela metade (só servidor) pede o outro", () => {
    const built = buildSizingBody("table", "mmc", mmc, text({ waitCost: "" }));
    expect(!built.ok && built.errors.waitCost).toBeTruthy();
  });
  it("custo mínimo exige servidor e espera", () => {
    const built = buildSizingBody("cost", "mmc", mmc, text({ serverCost: "", waitCost: "" }));
    expect(!built.ok && built.errors.serverCost && built.errors.waitCost).toBeTruthy();
  });
  it("menor c pela meta exige t e meta, e não leva custos nem faixa", () => {
    const missing = buildSizingBody("sla", "mmc", mmc, text({ t: "", target: "" }));
    expect(!missing.ok && missing.errors.t && missing.errors.target).toBeTruthy();
    const body = bodyOf(buildSizingBody("sla", "mmc", mmc, text({ cMin: "3" })))!;
    expect(body).toMatchObject({ t: 20, target: 0.8 });
    expect("server_cost" in body || "c_min" in body).toBe(false);
  });
  it("t sem meta (ou meta sem t) na tabela é recusado", () => {
    const built = buildSizingBody("table", "mmc", mmc, text({ target: "" }));
    expect(!built.ok && built.errors.target).toBeTruthy();
  });
});

describe("modelos com perda e de serviço geral", () => {
  it("Erlang-B: a meta é o bloqueio, sem t nem custo de espera, e o custo exige perda > 0", () => {
    const sla = bodyOf(buildSizingBody("sla", "erlangb", erlang, text()))!;
    expect(sla).toMatchObject({ model: "erlangb", mu: 1, servers: 15, target_blocking: 0.01 });
    expect("t" in sla || "target" in sla).toBe(false);
    const noLoss = buildSizingBody("cost", "erlangb", erlang, text({ lossCost: "" }));
    expect(!noLoss.ok && noLoss.errors.lossCost).toBeTruthy();
    const cost = bodyOf(buildSizingBody("cost", "erlangb", erlang, text({ lossCost: "7200", costUnit: "h" })))!;
    expect(cost.loss_cost).toBeCloseTo(2, 12);
    expect(cost.wait_cost).toBe(0);
  });
  it("M/M/c/K leva a capacidade e o custo de perda opcional", () => {
    const system: SystemText = { lambda: "25", mu: "10", servers: "3", capacity: "6" };
    const body = bodyOf(buildSizingBody("table", "mmck", system, text({ lossCost: "360", costUnit: "h" })))!;
    expect(body).toMatchObject({ model: "mmck", capacity: 6 });
    expect(body.loss_cost).toBeCloseTo(0.1, 12);
    const noLoss = bodyOf(buildSizingBody("table", "mmck", system, text()))!;
    expect("loss_cost" in noLoss).toBe(false);
  });
  it("M/M/1 e M/M/c usam c do Laboratório; o M/M/1 não envia servidores (c = 1 na API)", () => {
    const mm1: SystemText = { lambda: "40", mu: "50", servers: "1", capacity: "" };
    const body = bodyOf(buildSizingBody("table", "mm1", mm1, text()))!;
    expect(body).toMatchObject({ model: "mm1", lambda: 40, mu: 50 });
    expect("servers" in body).toBe(false);
  });
  it("M/G/c e M/G/1: serviço no lugar de μ", () => {
    const body = bodyOf(buildSizingBody("sla", "mgc", mgc, text({ t: "0.05" })))!;
    expect(body).toMatchObject({ model: "mgc", lambda: 80, servers: 10, service: { distribution: "lognormal", mean: 0.1, cv: 1.5 } });
    expect("mu" in body).toBe(false);
    const mg1 = bodyOf(buildSizingBody("sla", "mg1", { ...mgc, servers: "1" }, text()))!;
    expect(mg1.model).toBe("mg1");
    expect("servers" in mg1).toBe(false);
  });
  it("avisos de família: M/M/1, M/M/1/K, M/G/1 e M/M/c/K têm nota; M/M/c não", () => {
    expect(familyNote("mm1")).toContain("M/M/c");
    expect(familyNote("mm1k")).toContain("limitado a K");
    expect(familyNote("mg1")).toContain("M/G/c");
    expect(familyNote("mmck")).toContain("K");
    expect(familyNote("mmc")).toBeNull();
  });
});
