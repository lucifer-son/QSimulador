import { describe, expect, it } from "vitest";
import {
  buildSensitivityBody, buildServersBody, buildServicesBody, buildSweepBody, defaultMetric, loadFormula,
  sensitivityTexts, suggestRange, suggestServers, sweepVariables, type SystemText,
} from "./experiments";

const erlang: SystemText = { lambda: "20", mu: "1", servers: "15", capacity: "" };
const mgc: SystemText = {
  lambda: "80", mu: "", servers: "10", capacity: "", distribution: "lognormal", mean: "0.1", cv: "1.5",
};
const range = { start: "5", end: "40", step: "5" };
const noSim = { enabled: false, simulationTime: "2000", replications: "10", warmupTime: "100", seed: "2026" };
const lognormal = { distribution: "lognormal", mean: 0.1, cv: 1.5 };

describe("Erlang-B nos experimentos", () => {
  it("varre λ, μ e c (não há K: a capacidade é c)", () => {
    expect(sweepVariables("erlangb")).toEqual(["lambda", "mu", "servers"]);
  });
  it("varredura: envia λ, μ e c, sem capacidade", () => {
    const built = buildSweepBody("erlangb", "mu", erlang, range, noSim);
    expect(built).toEqual({
      ok: true, body: { model: "erlangb", variable: "mu", lambda: 20, servers: 15, start: 5, end: 40, step: 5 },
    });
  });
  it("comparar servidores: marca o modelo, envia μ e nunca a capacidade", () => {
    expect(buildServersBody("erlangb", erlang, "10, 15, 20", range)).toEqual({
      ok: true, body: { servers_list: [10, 15, 20], model: "erlangb", mu: 1, start: 5, end: 40, step: 5 },
    });
  });
  it("sensibilidade: λ, μ e c", () => {
    expect(buildSensitivityBody("erlangb", erlang, "10")).toEqual({
      ok: true, body: { model: "erlangb", lambda: 20, mu: 1, servers: 15, delta_pct: 10 },
    });
  });
  it("faixa de λ vai além de c·μ (a perda não satura) e a métrica inicial é o bloqueio", () => {
    expect(suggestRange("lambda", "erlangb", erlang)).toEqual({ start: "1.5", end: "24", step: "1.5" });
    expect(defaultMetric("erlangb")).toBe("p_block");
    expect(defaultMetric("mmc")).toBe("W");
    expect(suggestServers("erlangb", erlang)).toBe("14, 15, 16");
  });
  it("textos da sensibilidade citam só c", () => {
    expect(sensitivityTexts("erlangb").hint).toBe("De 0 a 50. c varia ±1.");
    expect(sensitivityTexts("mmck").effect("10")).toBe("λ e μ variam ±10%; c e K variam ±1 unidade.");
  });
});

describe("M/G/c nos experimentos", () => {
  it("varre λ, μ, c e a variabilidade do serviço", () => {
    expect(sweepVariables("mgc", "lognormal")).toEqual(["lambda", "mu", "servers", "cv"]);
    expect(sweepVariables("mgc", "erlang")).toEqual(["lambda", "mu", "servers", "k"]);
    expect(sweepVariables("mgc", "deterministic")).toEqual(["lambda", "mu", "servers"]);
    expect(sweepVariables("mg1", "lognormal")).toEqual(["lambda", "mu", "cv"]);      // o M/G/1 segue sem c
  });
  it("varredura de λ: serviço e c do Laboratório; varrendo c, não envia c", () => {
    const lambda = buildSweepBody("mgc", "lambda", mgc, range, noSim);
    expect(lambda.ok && lambda.body).toMatchObject({ model: "mgc", variable: "lambda", servers: 10, service: lognormal });
    const servers = buildSweepBody("mgc", "servers", mgc, { start: "7", end: "12", step: "1" }, noSim);
    expect(servers.ok && servers.body).toMatchObject({ model: "mgc", variable: "servers", lambda: 80, service: lognormal });
    expect(servers.ok && "servers" in servers.body).toBe(false);
  });
  it("comparar servidores: usa o serviço, não μ", () => {
    const built = buildServersBody("mgc", mgc, "9, 10, 11", range);
    expect(built).toEqual({
      ok: true, body: { servers_list: [9, 10, 11], model: "mgc", service: lognormal, start: 5, end: 40, step: 5 },
    });
  });
  it("comparar distribuições: c fixo do Laboratório; no M/G/1 o corpo não muda", () => {
    const built = buildServicesBody(mgc, ["lab", "deterministic"], range, "mgc");
    expect(built.ok && built.body).toMatchObject({ model: "mgc", servers: 10 });
    const mg1 = buildServicesBody({ ...mgc, servers: "1" }, ["lab", "deterministic"], range);
    expect(mg1.ok && "model" in mg1.body).toBe(false);
  });
  it("comparar distribuições sem c válido vira erro no campo", () => {
    const built = buildServicesBody({ ...mgc, servers: "" }, ["lab", "deterministic"], range, "mgc");
    expect(!built.ok && built.errors.servers).toBeTruthy();
  });
  it("sensibilidade: λ, serviço e c", () => {
    expect(buildSensitivityBody("mgc", mgc, "10")).toEqual({
      ok: true, body: { model: "mgc", lambda: 80, service: lognormal, servers: 10, delta_pct: 10 },
    });
    expect(sensitivityTexts("mgc").hint).toContain("c e o k do Erlang");
  });
  it("faixas sugeridas usam E[S] e c do Laboratório", () => {
    expect(suggestRange("lambda", "mgc", mgc)).toEqual({ start: "10", end: "120", step: "10" });   // c/E[S] = 100
    expect(suggestRange("servers", "mgc", mgc)).toEqual({ start: "1", end: "16", step: "1" });     // 2·λ·E[S]
    expect(suggestRange("mu", "mgc", mgc)).toEqual({ start: "4", end: "16", step: "0.8" });        // λ/c = 8
    expect(suggestServers("mgc", mgc)).toBe("9, 10, 11");
  });
  it("rótulo da carga oferecida por modelo", () => {
    expect([loadFormula("mg1"), loadFormula("mgc"), loadFormula("mmc"), loadFormula("erlangb")])
      .toEqual(["λ·E[S]", "λ·E[S]/c", "λ/(c·μ)", "λ/(c·μ)"]);
  });
});
