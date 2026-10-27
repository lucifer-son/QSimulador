import { describe, expect, it } from "vitest";
import { analysisConfig, formatP, hasDistributions, parseSampleFile, parseSampleText } from "./analysis";
import type { ViewResult } from "./types";

describe("parseSampleText", () => {
  it("separa por espaço, linha e ponto e vírgula, com vírgula decimal", () => {
    expect(parseSampleText("1,5\n2.25 3;4,75").values).toEqual([1.5, 2.25, 3, 4.75]);
  });
  it("vírgula entre vários números separa os valores", () => {
    expect(parseSampleText("1,2,3").values).toEqual([1, 2, 3]);
  });
  it("conta o que não é número e ignora vazios", () => {
    expect(parseSampleText("1 abc  \n 2 x1").ignored).toBe(2);
    expect(parseSampleText("").values).toEqual([]);
  });
});

describe("parseSampleFile", () => {
  it("usa a primeira coluna, pula o cabeçalho e o BOM", () => {
    const csv = "\ufefftempo,rotulo\n0.5,a\n1.25,b\n\n2,c\r\n";
    expect(parseSampleFile(csv)).toEqual({ values: [0.5, 1.25, 2], ignored: 0 });
  });
  it("aceita ponto e vírgula, vírgula decimal e conta linhas inválidas depois do cabeçalho", () => {
    expect(parseSampleFile("t;x\n1,5;a\n2,5;b\nxyz;c")).toEqual({ values: [1.5, 2.5], ignored: 1 });
  });
});

describe("pedidos", () => {
  const base = { lambda: 15, mu: 10 } as ViewResult["params"];
  it("modelo markoviano leva mu, c e K", () => {
    const body = analysisConfig({ modelKey: "mmck", params: { ...base, servers: 2, capacity: 6 } } as ViewResult);
    expect(body).toEqual({ model: "mmck", lambda: 15, mu: 10, servers: 2, capacity: 6 });
  });
  it("serviço geral vai aninhado em `service` e sem mu", () => {
    const body = analysisConfig({
      modelKey: "mgc",
      params: { lambda: 15, mu: 10, servers: 2, service: { distribution: "lognormal", values: { mean: 0.1, cv: 1.5 } } },
    } as unknown as ViewResult);
    expect(body).toEqual({ model: "mgc", lambda: 15, servers: 2, service: { distribution: "lognormal", mean: 0.1, cv: 1.5 } });
  });
  it("só o Erlang-B fica sem distribuições; o p-valor mostra < 0,001", () => {
    expect(hasDistributions("erlangb")).toBe(false);
    expect(hasDistributions("mmc")).toBe(true);
    expect(formatP(0.0004)).toBe("< 0,001");
    expect(formatP(0.4328)).toBe("0,433");
  });
});
