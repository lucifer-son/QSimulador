import { describe, expect, it } from "vitest";
import {
  formatCompactCount, formatInteger, formatMetric, formatNumber, formatPercentNumber, formatSignedPercent,
} from "./format";

describe("formatMetric", () => {
  it("mostra frações em porcentagem, com vírgula decimal", () => {
    expect(formatMetric("rho", 0.748)).toBe("74,8%");
    expect(formatMetric("rho", 0.748, { precise: true })).toBe("74,80%");
    expect(formatMetric("p_block", 0)).toBe("0,0%");
  });

  it("acrescenta a unidade de tempo e de vazão, e permite omiti-la", () => {
    expect(formatMetric("W", 0.13122, { precise: true })).toBe("0,13122 s");
    expect(formatMetric("W", 0.13122, { precise: true, unit: false })).toBe("0,13122");
    expect(formatMetric("throughput", 22.4396, { precise: true })).toBe("22,4396 req/s");
  });

  it("usa o mesmo número de dígitos, mantendo zeros à direita (alinha tabelas e intervalos)", () => {
    expect(formatMetric("W", 0.1306, { precise: true, unit: false })).toBe("0,13060");
    expect(formatMetric("W", 0.13176, { precise: true, unit: false })).toBe("0,13176");
    expect(formatMetric("throughput", 8, { precise: true })).toBe("8,00000 req/s");
    expect(formatMetric("throughput", 8.02463, { precise: true })).toBe("8,02463 req/s");
  });

  it("usa menos dígitos nos cartões (formato compacto)", () => {
    expect(formatMetric("L", 2.9444885)).toBe("2,944");
    expect(formatMetric("L", 2.9444885, { precise: true })).toBe("2,9445");
  });
});

describe("formatSignedPercent", () => {
  it("põe sinal em positivos e negativos (menos tipográfico)", () => {
    expect(formatSignedPercent(0.12)).toBe("+0,12%");
    expect(formatSignedPercent(-0.07)).toBe("−0,07%");
  });
  it("não põe sinal quando o valor arredondado é zero", () => {
    expect(formatSignedPercent(0.001)).toBe("0,00%");
    expect(formatSignedPercent(-0.001)).toBe("0,00%");
  });
});

describe("outros formatos", () => {
  it("formatPercentNumber", () => expect(formatPercentNumber(0.1234)).toBe("0,12%"));
  it("formatInteger usa ponto de milhar", () => expect(formatInteger(1234567)).toBe("1.234.567"));
  it("formatNumber remove zeros à direita", () => {
    expect(formatNumber(25)).toBe("25");
    expect(formatNumber(0.0312187)).toBe("0,0312187");
  });
  it("formatCompactCount abrevia contagens grandes", () => {
    expect(formatCompactCount(500_000)).toMatch(/^500\smil$/);
  });
});
