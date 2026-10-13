import { describe, expect, it } from "vitest";
import {
  buildSensitivityBody, buildServersBody, buildSweepBody, experimentFieldErrors, parseServerList,
  suggestRange, suggestServers, sweepVariables, type SystemText,
} from "./experiments";

const system: SystemText = { lambda: "25", mu: "10", servers: "3", capacity: "6" };
const range = { start: "5", end: "40", step: "5" };
const noSim = { enabled: false, simulationTime: "2000", replications: "10", warmupTime: "100", seed: "2026" };

describe("variáveis varridas", () => {
  it("c e K só aparecem nos modelos que os têm", () => {
    expect(sweepVariables("mm1")).toEqual(["lambda", "mu"]);
    expect(sweepVariables("mmc")).toEqual(["lambda", "mu", "servers"]);
    expect(sweepVariables("mm1k")).toEqual(["lambda", "mu", "capacity"]);
    expect(sweepVariables("mmck")).toEqual(["lambda", "mu", "servers", "capacity"]);
  });
});

describe("corpo da varredura", () => {
  it("envia os parâmetros fixos do modelo, sem o que é varrido", () => {
    const built = buildSweepBody("mmck", "lambda", system, range, noSim);
    expect(built).toEqual({
      ok: true,
      body: { model: "mmck", variable: "lambda", mu: 10, servers: 3, capacity: 6, start: 5, end: 40, step: 5 },
    });
  });

  it("não envia c nem K a modelos que não os têm", () => {
    const built = buildSweepBody("mm1", "mu", system, { start: "1", end: "3", step: "1" }, noSim);
    expect(built).toEqual({ ok: true, body: { model: "mm1", variable: "mu", lambda: 25, start: 1, end: 3, step: 1 } });
  });

  it("aceita vírgula decimal", () => {
    const built = buildSweepBody("mm1", "lambda", system, { start: "0,5", end: "2,5", step: "0,5" }, noSim);
    expect(built.ok && built.body.start).toBe(0.5);
  });

  it("com simulação, inclui os campos; semente em branco não é enviada", () => {
    const sim = { ...noSim, enabled: true, seed: "" };
    const built = buildSweepBody("mm1", "lambda", system, range, sim);
    expect(built.ok && built.body).toMatchObject({
      simulate: true, simulation_time: 2000, replications: 10, warmup_time: 100,
    });
    expect(built.ok && "seed" in built.body).toBe(false);
  });

  it("sem simulação, os campos de simulação não vão", () => {
    const built = buildSweepBody("mm1", "lambda", system, range, noSim);
    expect(built.ok && "simulate" in built.body).toBe(false);
  });

  it("servers e capacity exigem faixa inteira", () => {
    const built = buildSweepBody("mmck", "servers", system, { start: "1", end: "5", step: "0,5" }, noSim);
    expect(built).toEqual({ ok: false, errors: { step: "Informe um número inteiro." } });
  });

  it("aponta cada campo com formato inválido, sem chamar a API", () => {
    const built = buildSweepBody("mmck", "lambda", { ...system, mu: "x" }, { start: "", end: "40", step: "abc" }, {
      ...noSim, enabled: true, replications: "2,5",
    });
    expect(built.ok).toBe(false);
    expect(!built.ok && Object.keys(built.errors).sort()).toEqual(["replications", "start", "step", "mu"].sort());
  });
});

describe("lista de servidores", () => {
  it("aceita vírgula, espaço e ponto e vírgula", () => {
    expect(parseServerList("1, 2 4;8")).toEqual([1, 2, 4, 8]);
  });
  it("recusa vazio e não inteiros", () => {
    expect(parseServerList("")).toBeNull();
    expect(parseServerList("1, 2.5")).toBeNull();
    expect(parseServerList("a")).toBeNull();
  });
});

describe("corpo da comparação de servidores", () => {
  it("M/M/c: não envia capacidade", () => {
    const built = buildServersBody("mmc", system, "1, 2, 3", range);
    expect(built).toEqual({ ok: true, body: { servers_list: [1, 2, 3], mu: 10, start: 5, end: 40, step: 5 } });
  });
  it("M/M/c/K: envia a capacidade do Laboratório", () => {
    const built = buildServersBody("mmck", system, "2, 4", range);
    expect(built.ok && built.body.capacity).toBe(6);
  });
  it("lista inválida vira erro no campo", () => {
    const built = buildServersBody("mmc", system, "um, dois", range);
    expect(!built.ok && built.errors.serversList).toBeTruthy();
  });
});

describe("corpo da sensibilidade", () => {
  it("leva todos os parâmetros do modelo e a perturbação", () => {
    expect(buildSensitivityBody("mmck", system, "10")).toEqual({
      ok: true, body: { model: "mmck", lambda: 25, mu: 10, servers: 3, capacity: 6, delta_pct: 10 },
    });
  });
  it("perturbação inválida é recusada", () => {
    const built = buildSensitivityBody("mm1", system, "dez");
    expect(!built.ok && built.errors.delta).toBeTruthy();
  });
});

describe("sugestões", () => {
  it("λ: de 10% a 120% da capacidade de atendimento c·μ", () => {
    expect(suggestRange("lambda", "mmck", system)).toEqual({ start: "3", end: "36", step: "3" });
    expect(suggestRange("lambda", "mm1", { ...system, mu: "50" })).toEqual({ start: "5", end: "60", step: "5" });
  });
  it("μ: em torno do mínimo necessário λ/c", () => {
    expect(suggestRange("mu", "mm1", { ...system, lambda: "40" })).toEqual({ start: "20", end: "80", step: "4" });
  });
  it("c: de 1 até cerca do dobro da carga oferecida", () => {
    expect(suggestRange("servers", "mmc", { ...system, lambda: "8", mu: "1" })).toEqual({ start: "1", end: "16", step: "1" });
  });
  it("K: de c até o dobro da capacidade, com no máximo uns 12 passos", () => {
    const r = suggestRange("capacity", "mmck", system);
    expect(r).toEqual({ start: "3", end: "12", step: "1" });
  });
  it("com campos inválidos no Laboratório, ainda sugere algo", () => {
    expect(suggestRange("lambda", "mm1", { lambda: "", mu: "", servers: "", capacity: "" }).step).toBe("0.1");
  });
  it("servidores a comparar: o do Laboratório e vizinhos", () => {
    expect(suggestServers("mmck", system)).toBe("2, 3, 4");
    expect(suggestServers("mmc", { ...system, servers: "1" })).toBe("1, 2");
    expect(suggestServers("mm1", system)).toBe("1, 2");
  });
});

describe("erros da API nos campos", () => {
  it("mapeia os campos da faixa e da lista", () => {
    expect(experimentFieldErrors([
      { field: "step", message: "step deve ser maior que zero." },
      { field: "servers_list", message: "ruim" },
      { field: "variable", message: "sem campo" },
    ], "invalid_parameter")).toEqual({ step: "step deve ser maior que zero.", serversList: "ruim" });
  });
  it("requisição inválida usa a mensagem genérica", () => {
    expect(experimentFieldErrors([{ field: "start", message: "x" }], "invalid_request"))
      .toEqual({ start: "Valor inválido para este campo." });
  });
});
