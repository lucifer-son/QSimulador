import { describe, expect, it } from "vitest";
import { ARRIVALS_PER_SECOND, describeSeconds, estimateCost, estimateText } from "./estimate";

describe("estimateCost", () => {
  it("multiplica λ × tempo × réplicas e divide pela velocidade do simulador", () => {
    const e = estimateCost(25, 2000, 10)!;
    expect(e.arrivals).toBe(500_000);
    expect(e.seconds).toBeCloseTo(500_000 / ARRIVALS_PER_SECOND);
  });
  it.each([[NaN, 1, 1], [1, NaN, 1], [0, 10, 10], [-1, 10, 10], [1, Infinity, 1]])(
    "devolve null para entradas inválidas (%s, %s, %s)",
    (l, t, r) => expect(estimateCost(l, t, r)).toBeNull(),
  );
});

describe("describeSeconds", () => {
  it.each([
    [0.4, "menos de 1 s"],
    [6.25, "cerca de 6 s"],
    [59, "cerca de 59 s"],
    [120, "cerca de 2 min"],
  ])("%s s -> %s", (s, text) => expect(describeSeconds(s)).toBe(text));
});

describe("estimateText", () => {
  it("monta o texto a partir dos campos do formulário", () => {
    expect(estimateText("25", "2000", "10")).toMatch(/^500\smil chegadas, cerca de 6 s$/);
  });
  it("aceita vírgula decimal", () => {
    expect(estimateText("2,5", "2000", "10")).not.toBeNull();
  });
  it("devolve null se algum campo for inválido", () => {
    expect(estimateText("abc", "2000", "10")).toBeNull();
    expect(estimateText("25", "", "10")).toBeNull();
  });
});
