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
import { createRecord, deleteRecord, getRecord, getRecordsStatus, listRecords, renameRecord } from "../api/records";
import { runSensitivity, runServerComparison, runSweep } from "../api/experiments";
import { fieldErrorsFromApi } from "../api/fieldErrors";
import { buildReport, compareSimulated, type LevelsImport } from "../api/realdataExtra";
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

  it("todos os modelos trazem o P0, no analítico e na comparação (RF-03 e RF-31)", async () => {
    for (const model of MODEL_ORDER) {
      for (const action of ["calculate", "compare"] as const) {
        const r = await runAction(model, action, PARAMS[model]);
        const p0 = r.metrics.find((m) => m.name === "p0");
        expect(p0, `${model}/${action}`).toBeDefined();
        expect(p0!.analytical!).toBeGreaterThan(0);
        expect(p0!.analytical!).toBeLessThanOrEqual(1);
        if (action === "compare") expect(p0!.simulated).toBeTypeOf("number");
      }
      const names = (await runAction(model, "compare", PARAMS[model])).metrics.map((m) => m.name);
      expect(names.slice(0, 6)).toEqual(["rho", "L", "Lq", "W", "Wq", "p0"]); // ordem da especificação
    }
  });

  it("menos de 2 réplicas é recusado, e o erro identifica o campo", async () => {
    for (const model of MODEL_ORDER) {
      const error = await runAction(model, "compare", { ...PARAMS[model], replications: 1 }).catch((e: unknown) => e);
      expect(error, model).toBeInstanceOf(ApiError);
      expect((error as ApiError).code).toBe("invalid_parameter");
      expect((error as ApiError).fields?.map((f) => f.field)).toEqual(["replications"]);
      expect(Object.keys(fieldErrorsFromApi(error as ApiError))).toEqual(["replications"]);
    }
  });

  it("os erros de regra trazem o campo (e os de formato também)", async () => {
    const base = import.meta.env.VITE_API_BASE_URL as string;
    const post = async (path: string, body: object) => {
      const r = await fetch(`${base}${path}`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });
      return { status: r.status, body: (await r.json()) as { code: string; fields?: { field: string }[] } };
    };
    const unstable = await post("/api/models/mmc/calculate", { lambda: 20, mu: 1, servers: 10 });
    expect([unstable.status, unstable.body.code, unstable.body.fields?.[0].field]).toEqual([422, "unstable_system", "lambda"]);
    const tooBig = await post("/api/models/mm1/simulate", { lambda: 40, mu: 50, simulation_time: 100000, replications: 2 });
    expect([tooBig.body.code, tooBig.body.fields?.[0].field]).toEqual(["invalid_parameter", "simulation_time"]);
    const missing = await post("/api/models/mmc/calculate", { mu: 1 });
    expect(missing.body.code).toBe("invalid_request");
    expect(missing.body.fields?.map((f) => f.field)).toContain("lambda");
  });

  it("as fixtures de erro têm o formato real da API", async () => {
    const base = import.meta.env.VITE_API_BASE_URL as string;
    const shape = async (path: string, body: object) =>
      Object.keys(await (await fetch(`${base}${path}`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) })).json()).sort();
    expect(await shape("/api/models/mmc/calculate", { lambda: 20, mu: 1, servers: 10 })).toEqual(keys(fixtures.errorUnstable));
    expect(await shape("/api/models/mmck/calculate", { lambda: 1, mu: 1, servers: 3, capacity: 2 })).toEqual(keys(fixtures.errorInvalidParameter));
    expect(await shape("/api/models/mmck/simulate", { ...PARAMS.mmck, replications: 1 })).toEqual(keys(fixtures.errorReplications));
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

  describe("dados reais: acréscimos da Fase 7 (JSON)", () => {
    const SIM = { simulation_time: 200, replications: 3, warmup_time: 10, confidence_level: 0.95, seed: 7 };
    const imported = fixtures.realdataLevelsImport as unknown as LevelsImport;

    it("comparação com simulação: formato igual ao da fixture e semente devolvida", async () => {
      const { levels, suggestions } = imported;
      const r = await compareSimulated({
        model: "mm1n", mu: suggestions.mu as number, servers: 1, think_time: suggestions.think_time as number,
        levels, simulation: SIM,
      });
      expect(keys(r)).toEqual(keys(fixtures.realdataCompareSimulated));
      expect(keys(r.simulation)).toEqual(keys(fixtures.realdataCompareSimulated.simulation));
      expect(keys(r.comparison[0].metrics.W)).toEqual(keys(fixtures.realdataCompareSimulated.comparison[0].metrics.W));
      expect(r.simulation?.seed).toBe(7);
    });

    it("relatório: formato igual ao da fixture", async () => {
      const r = await buildReport({ format: "markdown", levels_import: imported });
      expect(keys(r)).toEqual(keys(fixtures.realdataReport));
      expect(r.filename).toBe("relatorio-experimental.md");
      expect(r.content).toContain("CSV agregado");
    });

    it("erro de regra na simulação chega com o campo", async () => {
      const { levels, suggestions } = imported;
      const bad = await compareSimulated({
        model: "mm1n", mu: suggestions.mu as number, servers: 1, think_time: suggestions.think_time as number,
        levels, simulation: { ...SIM, replications: 1 },
      }).catch((e: unknown) => e);
      expect(bad).toBeInstanceOf(ApiError);
      expect((bad as ApiError).fields?.[0].field).toBe("replications");
    });
  });

  describe("experimentos (Fase 6)", () => {
    it("varredura: formato igual ao das fixtures, instáveis sinalizados", async () => {
      const r = await runSweep({ model: "mm1", variable: "lambda", mu: 50, start: 10, end: 60, step: 10 });
      expect(keys(r)).toEqual(keys(fixtures.experimentSweepMm1));
      expect(keys(r.points[0])).toEqual(keys(fixtures.experimentSweepMm1.points[0]));
      expect(r.points.map((p) => p.status)).toEqual(["ok", "ok", "ok", "ok", "unstable", "unstable"]);
    });

    it("varredura com simulação devolve a semente e o resumo por ponto", async () => {
      const r = await runSweep({
        model: "mmck", variable: "lambda", mu: 10, servers: 3, capacity: 6, start: 5, end: 15, step: 5,
        simulate: true, simulation_time: 100, replications: 3, warmup_time: 10, seed: 7,
      });
      expect(r.simulation?.seed).toBe(7);
      expect(keys(r.points[0].simulation)).toEqual(keys(r.points[0].metrics));
    });

    it("comparação de servidores: uma série por c", async () => {
      const r = await runServerComparison({ servers_list: [1, 2, 3], mu: 10, start: 5, end: 25, step: 5 });
      expect(keys(r)).toEqual(keys(fixtures.experimentServersMmc));
      expect(r.series.map((s) => s.servers)).toEqual([1, 2, 3]);
    });

    it("sensibilidade: formato igual ao das fixtures", async () => {
      const r = await runSensitivity({ model: "mm1", lambda: 40, mu: 50, delta_pct: 25 });
      expect(keys(r)).toEqual(keys(fixtures.experimentSensitivityMm1));
      expect(r.parameters[0].high.status).toBe("unstable");
    });

    it("parâmetro inválido volta no formato de erro do projeto, com o campo", async () => {
      const error = await runSweep({ model: "mm1", variable: "lambda", mu: 50, start: 1, end: 5, step: 0 })
        .catch((e: unknown) => e);
      expect(error).toBeInstanceOf(ApiError);
      expect((error as ApiError).code).toBe("invalid_parameter");
      expect((error as ApiError).fields?.[0].field).toBe("step");
    });
  });
});

/**
 * Histórico: precisa de uma API com banco (QSIMULADOR_DATABASE_URL). Sem banco, o teste é ignorado.
 * Confere o ciclo completo e que o JSON volta exatamente como foi gravado (RF-26).
 */
describe.skipIf(!live)("contrato do histórico (/api/records)", () => {
  it("salva, lista, reabre, renomeia e exclui, devolvendo os mesmos dados", async (ctx) => {
    const status = await getRecordsStatus();
    if (!status.enabled) ctx.skip();

    const result = { rho: 0.1 + 0.2, tiny: 1e-9, texto: "λ ≤ μ", lista: [1, 2.5, { x: null }], flag: true };
    const params = { origin: "contrato", lambda: 40, mu: 50 };
    const saved = await createRecord({ kind: "simulation", title: "contrato", params, result });
    try {
      const page = await listRecords({ kind: "simulation", limit: 100 });
      expect(page.items.some((i) => i.id === saved.id)).toBe(true);

      const back = await getRecord(saved.id);
      expect(back.params).toEqual(params);
      expect(back.result).toEqual(result);

      expect((await renameRecord(saved.id, "novo título")).title).toBe("novo título");
    } finally {
      await deleteRecord(saved.id);
    }
    const gone = await getRecord(saved.id).catch((e: unknown) => e);
    expect(gone).toBeInstanceOf(ApiError);
    expect((gone as ApiError).code).toBe("record_not_found");
  });
});

// Evita um aviso de "arquivo sem testes" quando o contrato está desligado.
it("contrato desligado sem VITE_API_BASE_URL", () => {
  expect(MODELS.mm1.label).toBe("M/M/1");
});
