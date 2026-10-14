import { describe, expect, it } from "vitest";
import type { AnalysisResponse } from "../api/realdata";
import { clone, fixtures } from "../test/helpers";
import {
  bannerTone, buildAnalyzeForm, compareBody, errorsFromApi, INITIAL_TEXT, MAX_UPLOAD_BYTES, modelOptions,
} from "./realdata";

const analysis = () => clone(fixtures.realdataAnalyzeClosed) as unknown as AnalysisResponse;
const csv = (name = "teste.csv", size = 100) => {
  const file = new File(["x".repeat(size)], name, { type: "text/csv" });
  return file;
};

describe("buildAnalyzeForm", () => {
  it("exige um arquivo .csv, não vazio e dentro do limite", () => {
    expect(buildAnalyzeForm(null, INITIAL_TEXT)).toMatchObject({ ok: false, errors: { file: expect.stringContaining("Escolha") } });
    expect(buildAnalyzeForm(csv("dados.txt"), INITIAL_TEXT)).toMatchObject({ ok: false, errors: { file: expect.stringContaining(".csv") } });
    expect(buildAnalyzeForm(csv("a.csv", 0), INITIAL_TEXT)).toMatchObject({ ok: false, errors: { file: expect.stringContaining("vazio") } });
    const grande = csv();
    Object.defineProperty(grande, "size", { value: MAX_UPLOAD_BYTES + 1 });
    expect(buildAnalyzeForm(grande, INITIAL_TEXT)).toMatchObject({ ok: false, errors: { file: expect.stringContaining("limite") } });
  });

  it("só envia o que foi preenchido e aceita vírgula decimal", () => {
    const built = buildAnalyzeForm(csv(), { ...INITIAL_TEXT, systemType: "open", servers: "3", serviceTime: "0,1" });
    expect(built.ok).toBe(true);
    if (!built.ok) return;
    expect(built.form.get("system_type")).toBe("open");
    expect(built.form.get("servers")).toBe("3");
    expect(built.form.get("service_time_s")).toBe("0.1");
    expect(built.form.get("trim_start_pct")).toBe("10");
    expect(built.form.has("capacity")).toBe(false);
    expect(built.form.has("think_time_s")).toBe(false);
    expect((built.form.get("file") as File).name).toBe("teste.csv");
  });

  it.each([
    ["servers", "0"], ["servers", "1,5"], ["capacity", "-2"], ["serviceTime", "0"],
    ["thinkTime", "-1"], ["trimStart", "60"], ["trimEnd", ""], ["trimEnd", "abc"],
  ] as const)("rejeita %s = %j", (campo, valor) => {
    const built = buildAnalyzeForm(csv(), { ...INITIAL_TEXT, [campo]: valor });
    expect(built.ok).toBe(false);
    if (!built.ok) expect(Object.keys(built.errors)).toEqual([campo]);
  });

  it("aceita Z igual a zero (clientes sempre no sistema)", () => {
    expect(buildAnalyzeForm(csv(), { ...INITIAL_TEXT, thinkTime: "0" }).ok).toBe(true);
  });
});

describe("errorsFromApi", () => {
  it("traduz os campos da API para os do formulário", () => {
    expect(errorsFromApi([
      { field: "file", message: "ruim" }, { field: "service_time_s", message: "x" }, { field: "desconhecido", message: "y" },
    ])).toEqual({ file: "ruim", serviceTime: "x" });
    expect(errorsFromApi(undefined)).toEqual({});
  });
});

describe("recomparação com outro modelo (RF-24)", () => {
  it("oferece todos os modelos com μ e desabilita os que faltam dados", () => {
    const options = modelOptions(analysis());
    expect(options.map((o) => o.key).sort()).toEqual(["mm1", "mm1k", "mm1n", "mmc", "mmck", "mmcn"]);
    expect(options.find((o) => o.key === "mm1k")?.disabled).toMatch(/capacidade/);
    expect(options.find((o) => o.key === "mm1n")?.disabled).toBeNull();
  });

  it("desabilita população finita quando falta o número de usuários", () => {
    const result = analysis();
    result.levels[0].users = null;
    expect(modelOptions(result).find((o) => o.key === "mm1n")?.disabled).toMatch(/allThreads/);
  });

  it("monta o corpo da comparação com os parâmetros estimados e os níveis", () => {
    const result = analysis();
    const option = modelOptions(result).find((o) => o.key === "mm1n")!;
    const body = compareBody(result, option);
    expect(body).toMatchObject({ model: "mm1n", servers: 1, mu: option.mu });
    expect(body.think_time).toBeCloseTo(result.estimates.think_time!, 9);
    expect(body).not.toHaveProperty("capacity");
    expect(body.levels).toHaveLength(4);
  });
});

describe("bannerTone", () => {
  it("combina o status e a confiança", () => {
    const base = analysis();
    expect(bannerTone({ ...base, status: "recommended", confidence: "alta" })).toBe("success");
    expect(bannerTone({ ...base, status: "recommended", confidence: "media" })).toBe("info");
    expect(bannerTone({ ...base, status: "recommended", confidence: "baixa" })).toBe("warning");
    expect(bannerTone({ ...base, status: "no_good_fit", confidence: "alta" })).toBe("warning");
  });
});
