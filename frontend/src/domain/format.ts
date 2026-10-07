import { METRIC_INFO } from "./metrics";
import type { MetricName } from "./types";

const LOCALE = "pt-BR";
const fixed = (digits: number) =>
  new Intl.NumberFormat(LOCALE, { minimumFractionDigits: digits, maximumFractionDigits: digits });
const significant = (digits: number) =>
  new Intl.NumberFormat(LOCALE, { maximumSignificantDigits: digits });
/** Mesmo número de dígitos em todos os valores (mantém zeros à direita), para alinhar tabelas. */
const fixedSignificant = (digits: number) =>
  new Intl.NumberFormat(LOCALE, { minimumSignificantDigits: digits, maximumSignificantDigits: digits });

interface MetricFormatOptions {
  /** Mais casas decimais (tabelas). Cartões usam o formato compacto. */
  precise?: boolean;
  /** Acrescenta a unidade (s, req/s). */
  unit?: boolean;
}

export function formatMetric(
  name: MetricName,
  value: number,
  { precise = false, unit = true }: MetricFormatOptions = {},
): string {
  switch (METRIC_INFO[name].kind) {
    case "fraction":
      return `${fixed(precise ? 2 : 1).format(value * 100)}%`;
    case "count":
      return fixedSignificant(precise ? 5 : 4).format(value);
    case "time":
      return `${fixedSignificant(precise ? 5 : 4).format(value)}${unit ? " s" : ""}`;
    case "rate":
      return `${fixedSignificant(precise ? 6 : 4).format(value)}${unit ? " req/s" : ""}`;
  }
}

/** Ex.: 0.0012 -> "+0,12%" ; -0.0007 -> "−0,07%". Zero arredondado fica sem sinal. */
export function formatSignedPercent(percentPoints: number, digits = 2): string {
  const rounded = Number(Math.abs(percentPoints).toFixed(digits));
  const sign = rounded === 0 ? "" : percentPoints > 0 ? "+" : "−";
  return `${sign}${fixed(digits).format(rounded)}%`;
}

export function formatPercentNumber(percentPoints: number, digits = 2): string {
  return `${fixed(digits).format(percentPoints)}%`;
}

export function formatCompactCount(value: number): string {
  return new Intl.NumberFormat(LOCALE, { notation: "compact", maximumFractionDigits: 1 }).format(value);
}

export function formatInteger(value: number): string {
  return new Intl.NumberFormat(LOCALE, { maximumFractionDigits: 0 }).format(value);
}

export function formatNumber(value: number): string {
  return significant(6).format(value);
}
