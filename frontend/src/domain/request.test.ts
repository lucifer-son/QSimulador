import { describe, expect, it } from "vitest";
import { MODELS } from "./models";
import { buildBody, parseForm, parseNumber } from "./request";
import type { FormValues, ModelKey } from "./types";

const SIM = { simulationTime: "2000", replications: "10", warmupTime: "100", seed: "2026" };
const values = (model: ModelKey, extra: Partial<FormValues> = {}): FormValues => ({
  ...MODELS[model].example, ...SIM, ...extra,
});

describe("parseNumber", () => {
  it.each([["25", 25], ["1,5", 1.5], ["1.5", 1.5], [" 7 ", 7], ["1e3", 1000], ["-3", -3], [".5", 0.5], ["5.", 5]])(
    "aceita %j", (text, expected) => expect(parseNumber(text)).toBe(expected),
  );
  it.each([[""], ["  "], ["abc"], ["0x10"], ["1.2.3"], ["Infinity"], ["1,2,3"], ["--1"]])(
    "rejeita %j", (text) => expect(parseNumber(text)).toBeNaN(),
  );
});

describe("parseForm", () => {
  it("converte o formulário do M/M/c/K nos parâmetros numéricos", () => {
    const r = parseForm(values("mmck"), "mmck", "compare");
    expect(r).toEqual({
      ok: true,
      params: {
        lambda: 25, mu: 10, servers: 3, capacity: 6,
        simulationTime: 2000, replications: 10, warmupTime: 100, seed: 2026,
      },
    });
  });

  it("ignora os campos que o modelo não usa", () => {
    const r = parseForm(values("mm1", { servers: "lixo", capacity: "lixo" }), "mm1", "compare");
    expect(r.ok).toBe(true);
    if (r.ok) expect(r.params).toMatchObject({ servers: undefined, capacity: undefined });
    const c = parseForm(values("mmc", { capacity: "lixo" }), "mmc", "compare");
    expect(c.ok).toBe(true);
  });

  it("não exige os campos de simulação ao só calcular", () => {
    const r = parseForm(values("mmck", { simulationTime: "", replications: "x", seed: "?" }), "mmck", "calculate");
    expect(r.ok).toBe(true);
    if (r.ok) expect(r.params.simulationTime).toBeUndefined();
  });

  it("semente vazia significa aleatória", () => {
    const r = parseForm(values("mm1", { seed: "  " }), "mm1", "simulate");
    expect(r.ok).toBe(true);
    if (r.ok) expect(r.params.seed).toBeUndefined();
  });

  it("aponta o campo com problema de formato", () => {
    const r = parseForm(values("mmck", { lambda: "abc" }), "mmck", "compare");
    expect(r).toEqual({ ok: false, errors: { lambda: "Informe um número." } });
  });

  it("exige inteiro em servidores, capacidade, réplicas e semente", () => {
    const r = parseForm(values("mmck", { servers: "2,5", capacity: "6.1", replications: "1.5", seed: "3.3" }), "mmck", "compare");
    expect(r.ok).toBe(false);
    if (!r.ok) {
      expect(r.errors).toEqual({
        servers: "Informe um número inteiro.", capacity: "Informe um número inteiro.",
        replications: "Informe um número inteiro.", seed: "Informe um número inteiro.",
      });
    }
  });

  it("não valida regras do domínio (isso é da API)", () => {
    // λ ≥ c·μ, capacity < servers e valores negativos passam: quem decide é a API.
    const r = parseForm(values("mmck", { lambda: "-5", capacity: "1" }), "mmck", "compare");
    expect(r.ok).toBe(true);
  });
});

describe("buildBody", () => {
  const params = {
    lambda: 25, mu: 10, servers: 3, capacity: 6,
    simulationTime: 2000, replications: 10, warmupTime: 100, seed: 2026,
  };

  it("M/M/1: só lambda e mu, mais a simulação", () => {
    expect(buildBody("mm1", params, "compare")).toEqual({
      lambda: 25, mu: 10, simulation_time: 2000, replications: 10, warmup_time: 100, seed: 2026,
    });
  });
  it("M/M/c acrescenta servers; M/M/1/K acrescenta capacity; M/M/c/K os dois", () => {
    expect(buildBody("mmc", params, "simulate")).toHaveProperty("servers", 3);
    expect(buildBody("mmc", params, "simulate")).not.toHaveProperty("capacity");
    expect(buildBody("mm1k", params, "simulate")).toHaveProperty("capacity", 6);
    expect(buildBody("mm1k", params, "simulate")).not.toHaveProperty("servers");
    expect(buildBody("mmck", params, "simulate")).toMatchObject({ servers: 3, capacity: 6 });
  });
  it("calcular não leva campos de simulação", () => {
    expect(buildBody("mmck", params, "calculate")).toEqual({ lambda: 25, mu: 10, servers: 3, capacity: 6 });
  });
  it("omite a semente quando ela não foi informada", () => {
    expect(buildBody("mm1", { ...params, seed: undefined }, "compare")).not.toHaveProperty("seed");
  });
});
