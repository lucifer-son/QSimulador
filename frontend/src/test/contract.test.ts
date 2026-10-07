/**
 * Teste de contrato: roda o cliente do frontend contra a API real.
 * Só executa quando VITE_API_BASE_URL aponta para uma API no ar; sem isso, é ignorado.
 *
 *   PowerShell:  $env:VITE_API_BASE_URL="http://127.0.0.1:8000"; npm run test:contract
 *   bash:        VITE_API_BASE_URL=http://127.0.0.1:8000 npm run test:contract
 */
import { describe, expect, it } from "vitest";
import { fetchRuns, runAction } from "../api/actions";
import { ApiError } from "../api/client";
import { fieldErrorsFromApi } from "../api/fieldErrors";
import { MODEL_ORDER, MODELS } from "../domain/models";
import type { Action, ModelKey, Params } from "../domain/types";
import { fixtures } from "./helpers";

const live = Boolean(import.meta.env.VITE_API_BASE_URL);

const SIM = { simulationTime: 100, replications: 3, warmupTime: 10, seed: 7 };
const PARAMS: Record<ModelKey, Params> = {
  mm1: { lambda: 40, mu: 50, ...SIM },
  mmc: { lambda: 8, mu: 1, servers: 10, ...SIM },
  mm1k: { lambda: 12, mu: 10, capacity: 5, ...SIM },
  mmck: { lambda: 25, mu: 10, servers: 3, capacity: 6, ...SIM },
};
const ACTIONS: Action[] = ["calculate", "simulate", "compare"];
const keys = (o: unknown) => Object.keys(o as object).sort();

describe.skipIf(!live)("contrato com a API real", () => {
  describe.each(MODEL_ORDER)("%s", (model) => {
    it.each(ACTIONS)("%s devolve o formato que o cliente espera", async (action) => {
      const r = await runAction(model, action, PARAMS[model]);
      expect(r.action).toBe(action);
      expect(r.modelKey).toBe(model);
      expect(r.modelLabel).toMatch(/^M\/M\//);
      expect(r.metrics.length).toBeGreaterThanOrEqual(5);
      for (const m of r.metrics) {
        if (action !== "simulate") expect(m.analytical, m.name).toBeTypeOf("number");
        if (action !== "calculate") {
          expect(m.simulated, m.name).toBeTypeOf("number");
          expect(m.ciLow, m.name).toBeTypeOf("number");
        }
      }
      if (action !== "calculate") {
        expect(r.seed).toBe(7);
        expect(r.replications).toBe(3);
      }
      if (action === "compare") {
        expect(r.allWithinCi === null || typeof r.allWithinCi === "boolean").toBe(true);
        expect(r.maxErrorPct).toBeTypeOf("number");
      }
      if (action === "simulate") expect(r.runs).toHaveLength(3);
    });

    it("compare e simulate com a mesma semente dão a mesma simulação (base das abas Gráficos e Réplicas)", async () => {
      const compared = await runAction(model, "compare", PARAMS[model]);
      const runs = await fetchRuns(compared);
      expect(runs).toHaveLength(3);
      const simulated = await runAction(model, "simulate", PARAMS[model]);
      for (const m of compared.metrics) {
        expect(simulated.metrics.find((x) => x.name === m.name)!.simulated).toBe(m.simulated);
      }
    });
  });

  it("usa servers e capacity conforme o modelo", async () => {
    const r = await runAction("mmck", "calculate", PARAMS.mmck);
    expect(r).toMatchObject({ modelLabel: "M/M/3/6", servers: 3, capacity: 6 });
    expect(await runAction("mmc", "calculate", PARAMS.mmc)).toMatchObject({ servers: 10, capacity: null });
    expect(await runAction("mm1", "calculate", PARAMS.mm1)).toMatchObject({ servers: 1, capacity: null });
  });

  it("sistema instável chega como unstable_system e vira erro no campo λ", async () => {
    const error = await runAction("mmc", "calculate", { ...PARAMS.mmc, lambda: 20 }).catch((e: unknown) => e);
    expect(error).toBeInstanceOf(ApiError);
    expect((error as ApiError).code).toBe("unstable_system");
    expect(Object.keys(fieldErrorsFromApi(error as ApiError))).toEqual(["lambda"]);
  });

  it("regra de domínio chega como invalid_parameter e aponta o campo", async () => {
    const error = await runAction("mmck", "calculate", { ...PARAMS.mmck, capacity: 2 }).catch((e: unknown) => e);
    expect((error as ApiError).code).toBe("invalid_parameter");
    expect(Object.keys(fieldErrorsFromApi(error as ApiError))).toEqual(["capacity"]);
  });

  it("cada ação nunca devolve NaN/Infinity (o JSON seria inválido)", async () => {
    for (const model of MODEL_ORDER) {
      const r = await runAction(model, "compare", PARAMS[model]);
      for (const m of r.metrics) expect(Number.isFinite(m.simulated), `${model}.${m.name}`).toBe(true);
    }
  });

  describe("as fixtures dos testes ainda têm o formato real da API", () => {
    const cases: [ModelKey, Action, unknown][] = [
      ["mm1", "calculate", fixtures.mm1Calculate], ["mm1", "simulate", fixtures.mm1Simulate], ["mm1", "compare", fixtures.mm1Compare],
      ["mmc", "calculate", fixtures.mmcCalculate], ["mmc", "simulate", fixtures.mmcSimulate], ["mmc", "compare", fixtures.mmcCompare],
      ["mmck", "calculate", fixtures.mmckCalculate], ["mmck", "simulate", fixtures.mmckSimulate], ["mmck", "compare", fixtures.mmckCompare],
    ];
    it.each(cases)("%s/%s", async (model, action, fixture) => {
      const raw = (await runAction(model, action, PARAMS[model])).raw as Record<string, unknown>;
      const saved = fixture as Record<string, unknown>;
      expect(keys(raw)).toEqual(keys(saved));
      for (const group of ["metrics", "summary"] as const) {
        if (group in raw) {
          expect(keys(raw[group])).toEqual(keys(saved[group]));
          const first = keys(raw[group])[0];
          expect(keys((raw[group] as Record<string, unknown>)[first]))
            .toEqual(keys((saved[group] as Record<string, unknown>)[first]));
        }
      }
      if ("runs" in raw) expect(keys((raw.runs as unknown[])[0])).toEqual(keys((saved.runs as unknown[])[0]));
    });
  });
});

// Evita um aviso de "arquivo sem testes" quando o contrato está desligado.
it("contrato desligado sem VITE_API_BASE_URL", () => {
  expect(MODELS.mm1.label).toBe("M/M/1");
});
