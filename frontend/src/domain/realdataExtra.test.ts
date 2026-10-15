import { describe, expect, it } from "vitest";
import {
  applySuggestions, buildLevelsCompare, buildLevelsForm, buildSimulation, INITIAL_LEVELS, INITIAL_SIM,
  levelsErrorsFromApi, needsCapacity, needsServers, needsThinkTime, simulationErrorsFromApi, toFieldText,
  validateLevelsFile,
} from "./realdataExtra";
import { fixtures as fx } from "../test/helpers";

const levels = fx.realdataLevelsImport.levels as Parameters<typeof buildLevelsCompare>[0];
const ON = { ...INITIAL_SIM, enabled: true };
const file = (name: string, size = 10) => new File(["x".repeat(size)], name, { type: "text/csv" });

describe("simulação opcional", () => {
  it("vem desligada por padrão", () => {
    expect(INITIAL_SIM.enabled).toBe(false);
  });

  it("monta o corpo, aceita vírgula e omite a semente em branco", () => {
    expect(buildSimulation({ ...ON, simulationTime: "500,5", seed: "" })).toEqual({
      ok: true,
      body: { simulation_time: 500.5, replications: 10, warmup_time: 50, confidence_level: 0.95 },
    });
    const r = buildSimulation(ON);
    expect(r.ok && r.body.seed).toBe(2026);
  });

  it("só confere o formato (as regras ficam na API)", () => {
    expect(buildSimulation({ ...ON, simulationTime: "", replications: "2,5", warmupTime: "x", seed: "1.5" })).toEqual({
      ok: false,
      errors: { simulationTime: "Informe um número.", replications: "Informe um número inteiro.", warmupTime: "Informe um número.", seed: "Informe um número inteiro." },
    });
  });

  it("traduz o campo da API para o do formulário", () => {
    expect(simulationErrorsFromApi([{ field: "replications", message: "mínimo 2" }, { field: "outro", message: "x" }]))
      .toEqual({ replications: "mínimo 2" });
  });
});

describe("modelos dos níveis de carga", () => {
  it("cada modelo pede só os campos que usa", () => {
    expect([needsServers("mm1n"), needsServers("mmcn"), needsServers("mmc")]).toEqual([false, true, true]);
    expect([needsCapacity("mm1k"), needsCapacity("mmck"), needsCapacity("mm1")]).toEqual([true, true, false]);
    expect([needsThinkTime("mm1n"), needsThinkTime("mmcn"), needsThinkTime("mm1")]).toEqual([true, true, false]);
  });

  it("aplica as sugestões sem sobrescrever o que o usuário digitou", () => {
    const s = fx.realdataLevelsImport.suggestions as Parameters<typeof applySuggestions>[1];
    const vazio = applySuggestions(INITIAL_LEVELS, s);
    expect(vazio.mu).toBe(toFieldText(s.mu as number));
    expect(vazio.thinkTime).toBe(toFieldText(s.think_time as number));
    expect(applySuggestions({ ...INITIAL_LEVELS, mu: "7", thinkTime: "2" }, s)).toMatchObject({ mu: "7", thinkTime: "2" });
    expect(applySuggestions(INITIAL_LEVELS, { ...s, think_time: null, think_source: null }).thinkTime).toBe("");
  });

  it("toFieldText mantém 4 algarismos significativos", () => {
    expect(toFieldText(5.107252)).toBe("5.107");
  });
});

describe("arquivo", () => {
  it("valida extensão, vazio e tamanho antes de chamar a API", () => {
    expect(validateLevelsFile(null)).toMatch(/Escolha o arquivo/);
    expect(validateLevelsFile(file("a.txt"))).toMatch(/extensão .csv/);
    expect(validateLevelsFile(file("a.csv", 0))).toMatch(/vazio/);
    expect(validateLevelsFile(file("A.CSV"))).toBeNull();
    const grande = new File(["x"], "g.csv");
    Object.defineProperty(grande, "size", { value: 11 * 1024 * 1024 });
    expect(validateLevelsFile(grande)).toMatch(/10 MB/);
  });

  it("monta o multipart só com o arquivo", () => {
    const r = buildLevelsForm(file("n.csv"));
    expect(r.ok && (r.form.get("file") as File).name).toBe("n.csv");
    expect(buildLevelsForm(file("n.txt"))).toEqual({ ok: false, error: "O arquivo precisa ter a extensão .csv." });
  });
});

describe("buildLevelsCompare", () => {
  const closed = { ...INITIAL_LEVELS, mu: "5,1", thinkTime: "1" };

  it("modelo fechado: envia μ, Z e os níveis, sem simulação", () => {
    const r = buildLevelsCompare(levels, closed, INITIAL_SIM);
    expect(r).toEqual({ ok: true, simulated: false, body: { model: "mm1n", mu: 5.1, servers: 1, think_time: 1, levels } });
  });

  it("com 'Simular também' acrescenta o bloco simulation", () => {
    const r = buildLevelsCompare(levels, closed, ON);
    expect(r.ok && r.simulated).toBe(true);
    expect(r.ok && "simulation" in r.body && r.body.simulation.simulation_time).toBe(1000);
  });

  it("modelo aberto com capacidade não manda Z, e manda c e K", () => {
    const r = buildLevelsCompare(levels, { ...INITIAL_LEVELS, model: "mmck", mu: "5", servers: "3", capacity: "8", thinkTime: "9" }, INITIAL_SIM);
    expect(r.ok && r.body).toMatchObject({ model: "mmck", servers: 3, capacity: 8 });
    expect(r.ok && "think_time" in r.body).toBe(false);
  });

  it("aponta os campos com formato errado", () => {
    expect(buildLevelsCompare(levels, { ...INITIAL_LEVELS, mu: "", thinkTime: "abc" }, { ...ON, replications: "x" })).toEqual({
      ok: false,
      errors: { mu: "Informe um número.", thinkTime: "Informe um número.", replications: "Informe um número inteiro." },
    });
    const c = buildLevelsCompare(levels, { ...INITIAL_LEVELS, model: "mmcn", mu: "5", thinkTime: "1", servers: "1,5" }, INITIAL_SIM);
    expect(!c.ok && c.errors.servers).toBe("Informe um número inteiro.");
  });

  it("traduz erros da API, inclusive os da simulação", () => {
    expect(levelsErrorsFromApi([
      { field: "think_time", message: "falta Z" }, { field: "replications", message: "mínimo 2" }, { field: "file", message: "ruim" },
    ])).toEqual({ thinkTime: "falta Z", replications: "mínimo 2", file: "ruim" });
  });
});
