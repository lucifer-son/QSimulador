import { describe, expect, it } from "vitest";
import { MODELS } from "./models";
import {
  DISTRIBUTION_KEYS, DISTRIBUTIONS, distributionInfo, parseService, serviceMoments, serviceSummary, serviceToText,
} from "./service";
import type { FormValues } from "./types";

const SIM = { simulationTime: "2000", replications: "10", warmupTime: "100", seed: "2026" };
const form = (extra: Partial<FormValues> = {}): FormValues => ({ ...MODELS.mg1.example, ...SIM, ...extra });

describe("catálogo", () => {
  it("tem as oito distribuições na ordem da API (GET /api/distributions)", () => {
    expect(DISTRIBUTION_KEYS).toEqual([
      "deterministic", "exponential", "erlang", "lognormal", "weibull", "uniform", "triangular", "truncated_normal",
    ]);
  });

  it("média ou taxa para as quatro paramétricas; parâmetros próprios para as demais", () => {
    for (const d of DISTRIBUTIONS) expect(d.fields[0].field === "mean").toBe(d.meanBased);
    expect(distributionInfo("triangular").fields.map((f) => f.field)).toEqual(["min", "mode", "max"]);
    expect(distributionInfo("truncated_normal").fields.map((f) => f.field)).toEqual(["loc", "scale"]);
    expect(distributionInfo("erlang").fields[1]).toMatchObject({ field: "k", integer: true });
  });

  it("chave desconhecida cai na lognormal (padrão do formulário)", () => {
    expect(distributionInfo("gama").key).toBe("lognormal");
  });
});

describe("serviceMoments (confere com o backend)", () => {
  it("determinística, exponencial e Erlang", () => {
    expect(serviceMoments("deterministic", { mean: 2 })).toEqual({ mean: 2, std: 0, cv: 0, mu: 0.5 });
    expect(serviceMoments("exponential", { mean: 2 })).toMatchObject({ std: 2, cv: 1 });
    expect(serviceMoments("erlang", { mean: 2, k: 4 })).toMatchObject({ std: 1, cv: 0.5 });
  });

  it("lognormal e Weibull têm o CV pedido", () => {
    expect(serviceMoments("lognormal", { mean: 3, cv: 0.8 })!.cv).toBeCloseTo(0.8, 12);
    expect(serviceMoments("weibull", { mean: 3, cv: 2.5 })!.cv).toBeCloseTo(2.5, 12);
  });

  it("uniforme e triangular", () => {
    const u = serviceMoments("uniform", { min: 0.2, max: 0.8 })!;
    expect(u.mean).toBeCloseTo(0.5, 12);
    expect(u.std).toBeCloseTo(0.6 / Math.sqrt(12), 12);
    const t = serviceMoments("triangular", { min: 0, mode: 3, max: 6 })!;
    expect(t.mean).toBeCloseTo(3, 12);
    expect(t.std ** 2).toBeCloseTo(27 / 18, 12);
  });

  it("normal truncada: momentos da truncada (valores do scipy)", () => {
    const half = serviceMoments("truncated_normal", { loc: 0, scale: 1 })!;
    expect(half.mean).toBeCloseTo(0.7978845608, 6);          // √(2/π)
    expect(half.std ** 2).toBeCloseTo(1 - 2 / Math.PI, 6);
    const alta = serviceMoments("truncated_normal", { loc: 10, scale: 1 })!;
    expect(alta.mean).toBeCloseTo(10, 5);
    expect(alta.std).toBeCloseTo(1, 5);
    const comum = serviceMoments("truncated_normal", { loc: 0.02, scale: 0.02 })!;   // fixture do backend
    expect(comum.mean).toBeCloseTo(0.025751999418783568, 7);
    expect(comum.std ** 2).toBeCloseTo(0.00025187451431064216, 9);
  });

  it.each([
    ["exponential", { mean: 0 }], ["exponential", {}], ["erlang", { mean: 1, k: 2.5 }], ["erlang", { mean: 1, k: 0 }],
    ["lognormal", { mean: 1 }], ["uniform", { min: 3, max: 2 }], ["uniform", { min: -1, max: 2 }],
    ["triangular", { min: 1, mode: 5, max: 3 }], ["truncated_normal", { loc: 1, scale: 0 }],
  ] as const)("%s com %j não é uma distribuição válida", (key, values) => {
    expect(serviceMoments(key, values)).toBeNull();
  });
});

describe("parseService", () => {
  it("lê só os campos da distribuição escolhida", () => {
    const r = parseService(form({ distribution: "erlang", mean: "0,02", k: "4", cv: "lixo", min: "" }));
    expect(r).toEqual({ ok: true, service: { distribution: "erlang", values: { mean: 0.02, k: 4 } } });
  });

  it("aponta o campo inválido, sem olhar os que não são usados", () => {
    expect(parseService(form({ distribution: "uniform", min: "", max: "abc", mean: "lixo" }))).toEqual({
      ok: false, errors: { min: "Informe um número.", max: "Informe um número." },
    });
    const k = parseService(form({ distribution: "erlang", k: "2,5" }));
    expect(k).toEqual({ ok: false, errors: { k: "Informe um número inteiro." } });
  });
});

describe("serviceSummary", () => {
  it("resume E[S], desvio, CV, μ e ρ", () => {
    const text = serviceSummary(form({ lambda: "25", distribution: "lognormal", mean: "0.02", cv: "0.5" }))!;
    expect(text).toBe("E[S] = 0,02 s · desvio = 0,01 s · CV = 0,5 · μ = 50 req/s · ρ = 0,5");
  });

  it("não mostra ρ sem λ válido e some se o serviço é inválido", () => {
    expect(serviceSummary(form({ lambda: "" }))).not.toContain("ρ");
    expect(serviceSummary(form({ distribution: "uniform", min: "3", max: "2" }))).toBeNull();
    expect(serviceSummary(form({ mean: "abc" }))).toBeNull();
  });

  it("mostra a média calculada das distribuições de parâmetros próprios", () => {
    const text = serviceSummary(form({ distribution: "uniform", min: "0.01", max: "0.03" }))!;
    expect(text).toContain("E[S] = 0,02 s");
  });
});

describe("serviceToText", () => {
  it("devolve o formulário a partir dos números salvos", () => {
    expect(serviceToText({ distribution: "triangular", values: { min: 0.01, mode: 0.02, max: 0.05 } }))
      .toEqual({ distribution: "triangular", min: "0.01", mode: "0.02", max: "0.05" });
  });
});
