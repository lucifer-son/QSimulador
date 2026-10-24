import { describe, expect, it } from "vitest";
import {
  blankScenario, buildScenariosBody, estimateScenariosText, formatDelta, formatRelative, initialScenarios,
  parseOverride, scenarioFieldErrors, visibleVariables,
} from "./scenarios";
import { MODELS } from "./models";

const system = { ...MODELS.mmc.example };
const sim = { simulationTime: "2000", replications: "10", warmupTime: "100", seed: "2026" };

describe("parseOverride", () => {
  it("vazio é sem alteração", () => {
    expect(parseOverride("  ", false)).toEqual({ ok: true, override: null });
  });
  it("valor absoluto e percentual relativo em λ, μ e CV", () => {
    expect(parseOverride("12", false)).toEqual({ ok: true, override: { mode: "absolute", value: 12 } });
    expect(parseOverride("1,5", false)).toEqual({ ok: true, override: { mode: "absolute", value: 1.5 } });
    expect(parseOverride("+20%", false)).toEqual({ ok: true, override: { mode: "relative", value: 20 } });
    expect(parseOverride("−10 %", false)).toEqual({ ok: true, override: { mode: "relative", value: -10 } });
    expect(parseOverride("20%", false)).toEqual({ ok: true, override: { mode: "relative", value: 20 } });
  });
  it("em λ, μ e CV, sinal sem % é erro (a ambiguidade não é adivinhada)", () => {
    expect(parseOverride("+2", false).ok).toBe(false);
    expect(parseOverride("-2", false).ok).toBe(false);
  });
  it("c, K e k: absoluto, ou unidades com sinal; % e fração são erros", () => {
    expect(parseOverride("12", true)).toEqual({ ok: true, override: { mode: "absolute", value: 12 } });
    expect(parseOverride("+1", true)).toEqual({ ok: true, override: { mode: "relative", value: 1 } });
    expect(parseOverride("-2", true)).toEqual({ ok: true, override: { mode: "relative", value: -2 } });
    expect(parseOverride("+20%", true).ok).toBe(false);
    expect(parseOverride("2,5", true).ok).toBe(false);
  });
  it("lixo é erro", () => {
    for (const text of ["abc", "1x", "--1", "+", "%"]) expect(parseOverride(text, false).ok, text).toBe(false);
  });
});

describe("buildScenariosBody", () => {
  it("monta a base, os cenários e a simulação do Laboratório", () => {
    const built = buildScenariosBody("mmc", system, sim, initialScenarios("mmc"), false);
    expect(built).toEqual({
      ok: true,
      body: {
        base: { model: "mmc", lambda: 8, mu: 1, servers: 10 },
        scenarios: [
          { name: "+20% de λ", lambda: { mode: "relative", value: 20 } },
          { name: "+1 servidor", servers: { mode: "relative", value: 1 } },
        ],
        bonferroni: false, simulation_time: 2000, replications: 10, warmup_time: 100, seed: 2026,
      },
    });
  });
  it("sem semente no Laboratório, o pedido não leva seed", () => {
    const built = buildScenariosBody("mmc", system, { ...sim, seed: "" }, initialScenarios("mmc"), true);
    expect(built.ok && "seed" in built.body).toBe(false);
    expect(built.ok && built.body.bonferroni).toBe(true);
  });
  it("só confere o formato e aponta o campo do cenário", () => {
    const list = [{ ...blankScenario(7), lambda: "muito" }, { ...blankScenario(8), servers: "+20%" }];
    const built = buildScenariosBody("mmc", system, sim, list, false);
    expect(built.ok).toBe(false);
    if (!built.ok) expect(Object.keys(built.errors).sort()).toEqual(["s7.lambda", "s8.servers"]);
  });
  it("sem cenários e com simulação inválida", () => {
    const built = buildScenariosBody("mmc", system, { ...sim, replications: "2,5" }, [], false);
    expect(!built.ok && built.errors).toMatchObject({ scenarios: expect.any(String), replications: expect.any(String) });
  });
  it("campos que o modelo não tem são ignorados (K no M/M/c)", () => {
    const built = buildScenariosBody("mmc", system, sim, [{ ...blankScenario(1), capacity: "abc", lambda: "+5%" }], false);
    expect(built.ok).toBe(true);
  });
  it("trocar o modelo do cenário muda os campos (M/M/c/K ganha K)", () => {
    const s = { ...blankScenario(1), model: "mmck" as const, capacity: "20" };
    expect(visibleVariables("mmc", s)).toContain("capacity");
    expect(visibleVariables("mmc", blankScenario(1))).not.toContain("capacity");
    const built = buildScenariosBody("mmc", system, sim, [s], false);
    expect(built.ok && built.body.scenarios).toEqual([{ model: "mmck", capacity: { mode: "absolute", value: 20 } }]);
  });
});

describe("estimativa e formatação", () => {
  it("soma a base e os cenários, com o λ de cada um", () => {
    const text = estimateScenariosText(system, initialScenarios("mmc"), sim);
    // 8 + 9,6 + 8 = 25,6 req/s · 2000 s · 10 réplicas ≈ 512 mil chegadas, em 3 simulações
    expect(text).toMatch(/512\smil chegadas no total \(3 simulações\)/);
  });
  it("sem λ válido não estima", () => {
    expect(estimateScenariosText({ ...system, lambda: "x" }, initialScenarios("mmc"), sim)).toBeNull();
  });
  it("diferenças com sinal; frações em pontos percentuais", () => {
    expect(formatDelta("Wq", -0.11457)).toBe("−0,1146");
    expect(formatDelta("Wq", 1.6846)).toBe("+1,685");
    expect(formatDelta("rho", 0.05)).toBe("+5,00 p.p.");
    expect(formatDelta("rho", 0.000001)).toBe("0,00 p.p.");
    expect(formatRelative(-0.5944)).toBe("−59,4%");
    expect(formatRelative(null)).toBe("—");
  });
});

describe("scenarioFieldErrors", () => {
  const list = [blankScenario(4), blankScenario(9)];
  it("leva scenarios[i].campo para o campo do cenário certo", () => {
    const r = scenarioFieldErrors([{ field: "scenarios[1].cv", message: "cv só se aplica" }], "invalid_parameter", list);
    expect(r.fields).toEqual({ "s9.cv": "cv só se aplica" });
  });
  it("simulação e base", () => {
    const r = scenarioFieldErrors([
      { field: "replications", message: "r" }, { field: "base.lambda", message: "instável" }, { field: "scenarios", message: "n" },
    ], "invalid_parameter", list);
    expect(r.fields).toEqual({ replications: "r" });
    expect(r.general).toEqual(["Base (Laboratório): instável", "n"]);
  });
  it("erro de forma não repete a mensagem técnica", () => {
    const r = scenarioFieldErrors([{ field: "scenarios.0.lambda.mode", message: "Input should be" }], "invalid_request", list);
    expect(r.general).toEqual(["Valor inválido para este campo."]);
  });
});
