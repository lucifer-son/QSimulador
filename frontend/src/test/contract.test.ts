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
import { runSensitivity, runServerComparison, runServicesComparison, runSweep } from "../api/experiments";
import { fetchDistribution, fetchSensitivityCurve, streamFit, type FitEvent } from "../api/analysis";
import { exportScenariosCsv, streamScenarios, type ScenarioEvent } from "../api/scenarios";
import { runSizingCost, runSizingSla, runSizingTable } from "../api/sizing";
import { fieldErrorsFromApi } from "../api/fieldErrors";
import { buildReport, compareSimulated, type LevelsImport } from "../api/realdataExtra";
import { MODEL_ORDER, MODELS } from "../domain/models";
import type { Action, MarkovModelKey, Params } from "../domain/types";
import { fixtures, readBlobArrayBuffer, readBlobText } from "./helpers";

const live = Boolean(import.meta.env.VITE_API_BASE_URL);

const SIM = { simulationTime: 100, replications: 3, warmupTime: 10, seed: 7 };
const PARAMS: Record<MarkovModelKey, Params> = {
  mm1: { lambda: 40, mu: 50, ...SIM },
  mmc: { lambda: 8, mu: 1, servers: 10, ...SIM },
  mm1k: { lambda: 12, mu: 10, capacity: 5, ...SIM },
  mmck: { lambda: 25, mu: 10, servers: 3, capacity: 6, ...SIM },
};
const MG1_PARAMS: Params = {
  lambda: 25, mu: 50, ...SIM, service: { distribution: "lognormal", values: { mean: 0.02, cv: 0.5 } },
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

  describe("mg1 (serviço geral)", () => {
    it.each(ACTIONS)("%s devolve o formato que o cliente espera", async (action) => {
      const r = await runAction("mg1", action, MG1_PARAMS);
      expect(r.action).toBe(action);
      expect(r.modelLabel).toBe("M/G/1");
      expect(r.service).toMatchObject({ distribution: "lognormal", cv: 0.5, mu: 50 });
      expect(r.metrics.map((m) => m.name).slice(0, 6)).toEqual(["rho", "L", "Lq", "W", "Wq", "p0"]);
      if (action === "compare") expect(r.maxErrorPct).toBeTypeOf("number");
      if (action === "simulate") expect(r.runs).toHaveLength(3);
    });

    it("determinística vira M/D/1 e confere o valor de referência (Wq = 22,5 s com λ = 40/h, μ = 80/h)", async () => {
      const r = await runAction("mg1", "calculate", {
        lambda: 40, mu: 80, service: { distribution: "deterministic", values: { mu: 80 } as never },
      });
      expect(r.modelLabel).toBe("M/D/1");
      expect(r.metrics.find((m) => m.name === "Wq")!.analytical! * 3600).toBeCloseTo(22.5, 6);
    });

    it("sistema instável chega como unstable_system, com o campo λ", async () => {
      const error = await runAction("mg1", "calculate", {
        lambda: 60, mu: 0, service: { distribution: "uniform", values: { min: 0.01, max: 0.03 } },
      }).catch((e: unknown) => e as ApiError);
      expect(error).toBeInstanceOf(ApiError);
      expect((error as ApiError).code).toBe("unstable_system");
      expect(Object.keys(fieldErrorsFromApi(error as ApiError))).toEqual(["lambda"]);
    });

    it("as fixtures do M/G/1 ainda têm o formato real da API", async () => {
      for (const [action, fixture] of [["calculate", fixtures.mg1Calculate], ["simulate", fixtures.mg1Simulate], ["compare", fixtures.mg1Compare]] as const) {
        const raw = (await runAction("mg1", action, MG1_PARAMS)).raw as Record<string, unknown>;
        expect(keys(raw), action).toEqual(keys(fixture));
        expect(keys(raw.service), action).toEqual(keys((fixture as Record<string, unknown>).service));
      }
    });
  });

  describe("Fase 10: Erlang-B e M/G/c", () => {
    const EB: Params = { lambda: 20, mu: 1, servers: 15, ...SIM };
    const MGC: Params = {
      lambda: 80, mu: 10, servers: 10, ...SIM, service: { distribution: "lognormal", values: { mean: 0.1, cv: 1.5 } },
    };

    it.each(ACTIONS)("erlangb/%s devolve o formato que o cliente espera", async (action) => {
      const r = await runAction("erlangb", action, EB);
      expect(r.modelLabel).toBe("M/M/15/15");
      expect(r.capacity).toBe(15);
      expect(r.metrics.map((m) => m.name)).toEqual(
        action === "compare"
          ? ["rho", "L", "Lq", "W", "Wq", "throughput", "p_wait", "p_block"]   // P0 ≈ 1e-8 não é observável
          : ["rho", "L", "Lq", "W", "Wq", "p0", "throughput", "p_wait", "p_block"],
      );
      if (action === "calculate") expect(r.extras?.offered_load).toBe(20);
      if (action === "simulate") expect(r.runs).toHaveLength(3);
    });

    it.each(ACTIONS)("mgc/%s devolve o formato que o cliente espera", async (action) => {
      const r = await runAction("mgc", action, MGC);
      expect(r.modelLabel).toBe("M/G/10");
      if (action !== "simulate") expect(r.approximation).toEqual({ exact: false, warnings: [] });   // a simulação não traz
      expect(r.service?.distribution).toBe("lognormal");
      expect(r.service?.cv).toBeCloseTo(1.5, 10);
      if (action !== "simulate") {
        expect(r.metrics.map((m) => m.name)).toEqual(["rho", "L", "Lq", "W", "Wq", "throughput", "p_wait"]);
      }
      if (action === "simulate") expect(r.runs).toHaveLength(3);
    });

    it("mgc instável chega como unstable_system", async () => {
      const error = await runAction("mgc", "calculate", { ...MGC, lambda: 100 }).catch((e: unknown) => e as ApiError);
      expect((error as ApiError).code).toBe("unstable_system");
    });

    it("as fixtures da Fase 10 ainda têm o formato real da API", async () => {
      const cases = [
        ["erlangb", "calculate", EB, fixtures.erlangbCalculate], ["erlangb", "simulate", EB, fixtures.erlangbSimulate],
        ["erlangb", "compare", EB, fixtures.erlangbCompare], ["mgc", "calculate", MGC, fixtures.mgcCalculate],
        ["mgc", "simulate", MGC, fixtures.mgcSimulate], ["mgc", "compare", MGC, fixtures.mgcCompare],
      ] as const;
      for (const [model, action, params, fixture] of cases) {
        const raw = (await runAction(model, action, params as Params)).raw as Record<string, unknown>;
        expect(keys(raw), `${model}/${action}`).toEqual(keys(fixture));
      }
    });

    it("experimentos do M/G/1: varredura do CV, comparação de distribuições e sensibilidade", async () => {
      const service = { distribution: "lognormal", mean: 0.02, cv: 0.5 };
      const sweep = await runSweep({ model: "mg1", variable: "cv", start: 0.5, end: 2, step: 0.5, lambda: 25, service });
      expect(keys(sweep)).toEqual(keys(fixtures.experimentSweepMg1));
      expect(sweep.points.map((p) => p.status)).toEqual(["ok", "ok", "ok", "ok"]);
      const services = await runServicesComparison({
        services: [{ distribution: "deterministic", mean: 0.02 }, { distribution: "exponential", mean: 0.02 }, { ...service, cv: 1.5 }],
        start: 10, end: 50, step: 10,
      });
      expect(keys(services)).toEqual(keys(fixtures.experimentServicesMg1));
      expect(services.series).toHaveLength(3);
      const sens = await runSensitivity({ model: "mg1", lambda: 25, delta_pct: 10, service });
      expect(keys(sens)).toEqual(keys(fixtures.experimentSensitivityMg1));
      expect(sens.parameters.map((p) => p.name)).toEqual(["lambda", "mu", "cv"]);
    });
  });

  describe("as fixtures dos testes ainda têm o formato real da API", () => {
    const cases: [MarkovModelKey, Action, unknown][] = [
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
describe.skipIf(!live)("Fase 11: experimentos do Erlang-B e do M/G/c, e dimensionamento", () => {
  const service = { distribution: "lognormal", mean: 0.1, cv: 1.5 };

  it("Erlang-B e M/G/c: varredura, comparação de servidores e sensibilidade", async () => {
    const sweep = await runSweep({ model: "erlangb", variable: "lambda", mu: 1, servers: 10, start: 2, end: 20, step: 6 });
    expect(sweep.model).toBe("erlangb");
    expect(sweep.points.every((p) => p.status === "ok" && "p_block" in p.metrics!)).toBe(true);
    const servers = await runServerComparison({ model: "erlangb", servers_list: [5, 10], mu: 1, start: 2, end: 14, step: 4 });
    expect(servers.model).toBe("erlangb");
    const mgc = await runSweep({ model: "mgc", variable: "servers", lambda: 80, start: 9, end: 11, step: 1, service });
    expect(mgc.points.map((p) => p.status)).toEqual(["ok", "ok", "ok"]);
    const services = await runServicesComparison({
      model: "mgc", servers: 10, start: 10, end: 90, step: 40,
      services: [{ distribution: "deterministic", mean: 0.1 }, { distribution: "exponential", mean: 0.1 }],
    });
    expect(services.servers).toBe(10);
    const sens = await runSensitivity({ model: "mgc", lambda: 80, servers: 10, service });
    expect(sens.parameters.map((p) => p.name)).toEqual(["lambda", "mu", "servers", "cv"]);
  });

  it("dimensionamento: tabela, menor c pela meta e custo mínimo (referências das seções 3 e 7)", async () => {
    const callCenter = { model: "mmc", lambda: 90, mu: 15, t: 20 / 3600, target: 0.8 };
    expect((await runSizingSla(callCenter)).servers).toBe(9);
    expect((await runSizingTable({ ...callCenter, servers: 8 })).first_meeting_target).toBe(9);
    const cost = await runSizingCost({ model: "mmc", lambda: 50, mu: 6, server_cost: 35, wait_cost: 80 });
    expect(cost.optimal_servers).toBe(12);
    expect(cost.optimal_cost).toBeCloseTo(452, 0);
  });
});

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

describe.skipIf(!live)("contrato: comparação de cenários", () => {
  const body = {
    base: { model: "mmc", lambda: 8, mu: 1, servers: 10 },
    scenarios: [
      { name: "+20% de λ", lambda: { mode: "relative", value: 20 } },
      { name: "Sobrecarga", lambda: { mode: "relative", value: 50 } },
    ],
    simulation_time: 200, replications: 3, warmup_time: 20, seed: 7, bonferroni: false,
  };

  it("o fluxo NDJSON chega na ordem e com o formato que a tela espera", async () => {
    const events: ScenarioEvent[] = [];
    await streamScenarios(body, (e) => events.push(e));
    expect(events.map((e) => e.type)).toEqual(["start", "base", "scenario", "scenario", "done"]);
    const result = events.at(-1)!.result!;
    expect(result.settings.seed).toBe(7);
    expect(result.scenarios[0].metrics.Wq.diff?.n).toBe(3);
    expect(result.scenarios[1].status).toBe("unstable");
  });

  it("erro 422 traz o campo do cenário", async () => {
    const bad = { ...body, scenarios: [{ model: "mmck" }] };
    await expect(streamScenarios(bad, () => undefined)).rejects.toMatchObject({
      code: "invalid_parameter", fields: [{ field: "scenarios[0].capacity" }],
    });
  });

  it("o CSV sai com BOM e cabeçalho", async () => {
    const blob = await exportScenariosCsv(body);
    expect(new Uint8Array(await readBlobArrayBuffer(blob)).slice(0, 3)).toEqual(new Uint8Array([0xef, 0xbb, 0xbf]));
    expect((await readBlobText(blob)).startsWith("cenario,papel,modelo")).toBe(true);
  });
});

describe.skipIf(!live)("contrato: distribuições, sensibilidade e ajuste (Fase 13)", () => {
  const sim = { seed: 7, replications: 3, simulation_time: 100 };

  it("distribution: P(n) soma 1 e a fórmula fechada do M/M/c coincide com a gravada", async () => {
    const body = await fetchDistribution({ model: "mmc", lambda: 8, mu: 1, servers: 10, simulate: true, simulation: sim, points: 30 });
    expect(body.states!.p.reduce((a, b) => a + b, 0) + body.states!.omitted_mass).toBeCloseTo(1, 10);
    expect(keys(body)).toEqual(keys(fixtures.analysisDistributionMmc));
    expect(keys(body.wait_simulation)).toEqual(keys(fixtures.analysisDistributionMmc.wait_simulation));
    expect(body.wait_closed_form!.p_wait).toBeCloseTo(fixtures.analysisDistributionMmc.wait_closed_form!.p_wait, 12);
    expect(body.wait_simulation!.seed).toBe(7);
  });

  it("distribution: serviço geral não tem P(n); capacidade finita simula", async () => {
    const mgc = await fetchDistribution({
      model: "mgc", lambda: 15, servers: 2, service: { distribution: "lognormal", mean: 0.1, cv: 1.5 }, simulation: sim, points: 30,
    });
    expect(mgc.states).toBeNull();
    expect(keys(mgc)).toEqual(keys(fixtures.analysisDistributionMgc));
    const mmck = await fetchDistribution({ model: "mmck", lambda: 25, mu: 10, servers: 3, capacity: 6, simulation: sim, points: 30 });
    expect(mmck.states!.states).toEqual([0, 1, 2, 3, 4, 5, 6]);
    expect(mmck.wait_closed_form).toBeNull();
  });

  it("sensitivity: o ponto atual está na grade", async () => {
    const curve = await fetchSensitivityCurve({ model: "mm1", lambda: 40, mu: 50, points: 21 });
    expect(curve).toEqual(fixtures.analysisSensitivityMm1);
  });

  it("erros: Erlang-B (422 com o campo) e amostra curta", async () => {
    await expect(fetchDistribution({ model: "erlangb", lambda: 5, mu: 10, servers: 2 })).rejects.toMatchObject({
      code: "invalid_parameter", fields: [{ field: "model" }],
    });
    await expect(streamFit({ sample: [1, 2, 3] }, () => undefined)).rejects.toMatchObject({ fields: [{ field: "sample" }] });
  });

  it("fit: o fluxo NDJSON chega na ordem e reproduz a fixture com a mesma semente", async () => {
    const start = fixtures.analysisFitLognormal[0] as FitEvent;
    expect(start.seed).toBe(7);
    const sample = (await import("./fixtures/analysis-fit-sample.json")).default as number[];
    const events: FitEvent[] = [];
    await streamFit({ sample, bootstrap: 40, seed: 7 }, (e) => events.push(e));
    expect(events.map((e) => e.type)).toEqual(["start", "candidate", "candidate", "candidate", "candidate", "candidate", "done"]);
    expect(events).toEqual(fixtures.analysisFitLognormal);
  });

  it("fit: amostra constante sugere M/D/c", async () => {
    const events: FitEvent[] = [];
    await streamFit({ sample: Array(20).fill(2.5) }, (e) => events.push(e));
    expect(events.at(-1)!.result!.suggestion.model).toBe("M/D/c");
  });
});
