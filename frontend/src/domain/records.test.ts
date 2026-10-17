import { describe, expect, it } from "vitest";
import type { RecordDetail } from "../api/records";
import { fromCompare, type CompareResponse } from "../api/mappers";
import { fixtures as fx } from "../test/helpers";
import {
  experimentRecord, experimentTitle, labRecord, labTitle, parseExperimentRecord, parseLabRecord,
  parseRealDataRecord, realDataRecord, realDataTitle,
} from "./records";
import type { Params } from "./types";
import type { AnalysisResponse } from "../api/realdata";

const PARAMS: Params = { lambda: 25, mu: 10, servers: 3, capacity: 6, simulationTime: 2000, replications: 10, warmupTime: 100, seed: 2026 };
const lab = () => fromCompare("mmck", PARAMS, fx.mmckCompare as unknown as CompareResponse);

/** Como o servidor devolveria o que foi salvo. */
const stored = (r: { kind: string; title: string; params: Record<string, unknown>; result: Record<string, unknown> }): RecordDetail =>
  JSON.parse(JSON.stringify({
    id: "id-1", app_version: null, size_bytes: 1, created_at: "2026-10-15T12:00:00Z", updated_at: "2026-10-15T12:00:00Z", ...r,
  })) as RecordDetail;

describe("Laboratório", () => {
  it("título resume modelo, ação, λ e μ", () => {
    expect(labTitle(lab())).toBe("M/M/3/6 · Comparação (λ=25, μ=10)");
  });

  it("o tipo do registro vem da ação", () => {
    expect(labRecord(lab()).kind).toBe("comparison");
  });

  it("salvar e reabrir devolve o mesmo resultado", () => {
    const original = lab();
    const back = parseLabRecord(stored(labRecord(original)));
    expect(back).not.toBeNull();
    expect(back!.result).toEqual(JSON.parse(JSON.stringify(original)));
    expect(back!.parameters).toEqual(PARAMS);
    expect(back!.model).toBe("mmck");
    expect(back!.action).toBe("compare");
  });

  it("recusa registro de outra origem ou com formato inesperado", () => {
    const good = stored(labRecord(lab()));
    expect(parseLabRecord({ ...good, params: { ...good.params, origin: "outra" } })).toBeNull();
    expect(parseLabRecord({ ...good, params: { ...good.params, action: "x" } })).toBeNull();
    expect(parseLabRecord({ ...good, params: { ...good.params, model: "mm9" } })).toBeNull();
    expect(parseLabRecord({ ...good, params: { ...good.params, parameters: { lambda: "25" } } })).toBeNull();
    expect(parseLabRecord({ ...good, result: { ...good.result, metrics: "não é lista" } })).toBeNull();
    expect(parseLabRecord({ ...good, result: { ...good.result, modelKey: "mm1" } })).toBeNull();
  });
});

describe("Experimentos", () => {
  it("varredura: título e ida e volta", () => {
    const result = fx.experimentSweepMm1 as unknown as Record<string, unknown>;
    const model = (result.model as string) as "mm1";
    expect(experimentTitle("sweep", model, result as { variable?: string })).toMatch(/^Varredura de .+ · M\/M\/1$/);
    const rec = experimentRecord("sweep", model, { x: 1 }, result, "Minha curva");
    expect(rec.kind).toBe("experiment");
    const back = parseExperimentRecord(stored(rec));
    expect(back).toMatchObject({ type: "sweep", model });
    expect(back!.result).toEqual(result);
    expect(rec.params.request).toEqual({ x: 1 });
  });

  it("servidores e sensibilidade", () => {
    const servers = fx.experimentServersMmc as unknown as Record<string, unknown>;
    const sens = fx.experimentSensitivityMm1 as unknown as Record<string, unknown>;
    expect(parseExperimentRecord(stored(experimentRecord("servers", "mmc", null, servers, "s")))?.type).toBe("servers");
    expect(parseExperimentRecord(stored(experimentRecord("sensitivity", "mm1", null, sens, "s")))?.type).toBe("sensitivity");
    expect(experimentTitle("servers", "mmc", {})).toBe("Comparação de servidores · M/M/c");
    expect(experimentTitle("sensitivity", "mm1", {})).toBe("Sensibilidade · M/M/1");
  });

  it("recusa tipo errado de resultado", () => {
    const sweep = fx.experimentSweepMm1 as unknown as Record<string, unknown>;
    expect(parseExperimentRecord(stored(experimentRecord("servers", "mm1", null, sweep, "s")))).toBeNull();
    expect(parseExperimentRecord(stored({ kind: "experiment", title: "x", params: { origin: "experiment", experiment: "nada", model: "mm1" }, result: sweep }))).toBeNull();
    expect(parseExperimentRecord(stored({ kind: "experiment", title: "x", params: { origin: "lab" }, result: sweep }))).toBeNull();
  });
});

describe("Dados reais", () => {
  const analysis = fx.realdataAnalyzeClosed as unknown as AnalysisResponse;

  it("título cita o modelo e o número de amostras", () => {
    expect(realDataTitle(analysis)).toMatch(/^Análise do JMeter · .+ \(.+ amostras\)$/);
  });

  it("ida e volta", () => {
    const rec = realDataRecord(analysis, "Teste de carga");
    expect(rec.kind).toBe("realdata");
    const back = parseRealDataRecord(stored(rec));
    expect(back).toEqual(JSON.parse(JSON.stringify(analysis)));
  });

  it("recusa formato desconhecido", () => {
    const good = stored(realDataRecord(analysis));
    expect(parseRealDataRecord({ ...good, params: { ...good.params, source: "levels" } })).toBeNull();
    expect(parseRealDataRecord({ ...good, result: { dataset: 1 } })).toBeNull();
  });
});

describe("Laboratório: M/G/1", () => {
  const MG1: Params = {
    lambda: 25, mu: 50, simulationTime: 100, replications: 3, warmupTime: 10, seed: 7,
    service: { distribution: "lognormal", values: { mean: 0.02, cv: 0.5 } },
  };
  const mg1 = () => fromCompare("mg1", MG1, fx.mg1Compare as unknown as CompareResponse);

  it("o título descreve a distribuição e E[S] (não μ)", () => {
    expect(labTitle(mg1())).toBe("M/G/1 · Comparação (λ=25, Lognormal, E[S]=0.02)");
  });

  it("salvar e reabrir devolve a distribuição e o resultado", () => {
    const original = mg1();
    const snapshot = parseLabRecord(stored(labRecord(original)));
    expect(snapshot).not.toBeNull();
    expect(snapshot!.model).toBe("mg1");
    expect(snapshot!.parameters.service).toEqual(MG1.service);
    expect(snapshot!.result).toEqual(JSON.parse(JSON.stringify(original)));
  });

  it("registro do M/G/1 sem a distribuição não pode ser reaberto", () => {
    const record = labRecord(mg1());
    const params = record.params as { parameters: Record<string, unknown> };
    delete params.parameters.service;
    expect(parseLabRecord(stored(record))).toBeNull();
  });

  it("experimentos continuam restritos aos modelos markovianos", () => {
    const bad = stored({ kind: "experiment", title: "x", params: { origin: "experiment", experiment: "sweep", model: "mg1", request: null }, result: { points: [] } });
    expect(parseExperimentRecord(bad)).toBeNull();
  });
});

