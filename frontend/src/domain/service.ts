/**
 * Serviço geral (Fase 9): distribuições do tempo de serviço, no formulário do M/G/1.
 *
 * O catálogo abaixo espelha o da API (GET /api/distributions); um teste confere as chaves.
 * Os momentos (média, desvio, CV) são calculados aqui só para mostrar no formulário antes de
 * executar; quem vale é sempre o que a API devolve em `service`.
 */
import { formatNumber } from "./format";
import { parseNumber } from "./number";
import type {
  DistributionKey, FieldErrors, FormValues, ServiceParam, ServiceParams,
} from "./types";

export interface ServiceFieldInfo {
  field: ServiceParam;
  label: string;
  integer?: boolean;
  hint?: string;
}

export interface DistributionInfo {
  key: DistributionKey;
  label: string;
  /** Quando verdadeiro, o primeiro campo é a média E[S]; senão, a média é calculada. */
  meanBased: boolean;
  fields: ServiceFieldInfo[];
}

const MEAN: ServiceFieldInfo = { field: "mean", label: "Tempo médio E[S] (s)" };
const CV: ServiceFieldInfo = { field: "cv", label: "CV", hint: "De 0,01 a 10" };
const MIN: ServiceFieldInfo = { field: "min", label: "Mínimo (s)" };
const MAX: ServiceFieldInfo = { field: "max", label: "Máximo (s)" };

export const DISTRIBUTIONS: DistributionInfo[] = [
  { key: "deterministic", label: "Determinística (M/D/1)", meanBased: true, fields: [MEAN] },
  { key: "exponential", label: "Exponencial", meanBased: true, fields: [MEAN] },
  { key: "erlang", label: "Erlang-k", meanBased: true, fields: [MEAN, { field: "k", label: "Etapas k", integer: true, hint: "Inteiro ≥ 1" }] },
  { key: "lognormal", label: "Lognormal", meanBased: true, fields: [MEAN, CV] },
  { key: "weibull", label: "Weibull", meanBased: true, fields: [MEAN, CV] },
  { key: "uniform", label: "Uniforme", meanBased: false, fields: [MIN, MAX] },
  { key: "triangular", label: "Triangular", meanBased: false, fields: [MIN, { field: "mode", label: "Moda (s)" }, MAX] },
  {
    key: "truncated_normal", label: "Normal truncada em 0", meanBased: false,
    fields: [
      { field: "loc", label: "Média da normal (s)", hint: "Antes de truncar" },
      { field: "scale", label: "Desvio da normal (s)" },
    ],
  },
];

export const DISTRIBUTION_KEYS: DistributionKey[] = DISTRIBUTIONS.map((d) => d.key);
const BY_KEY = Object.fromEntries(DISTRIBUTIONS.map((d) => [d.key, d])) as Record<DistributionKey, DistributionInfo>;

export const isDistributionKey = (v: unknown): v is DistributionKey =>
  typeof v === "string" && v in BY_KEY;

export function distributionInfo(key: string): DistributionInfo {
  return isDistributionKey(key) ? BY_KEY[key] : BY_KEY.lognormal;
}

// ---------- momentos ----------

export interface ServiceMoments { mean: number; std: number; cv: number; mu: number }

/** erfc com erro relativo < 1,2e-7 (Numerical Recipes); basta para exibir 4 algarismos. */
function erfc(z: number): number {
  const x = Math.abs(z);
  const t = 1 / (1 + 0.5 * x);
  const poly =
    -1.26551223 + t * (1.00002368 + t * (0.37409196 + t * (0.09678418 + t * (-0.18628806 +
    t * (0.27886807 + t * (-1.13520398 + t * (1.48851587 + t * (-0.82215223 + t * 0.17087277))))))));
  const ans = t * Math.exp(-x * x + poly);
  return z >= 0 ? ans : 2 - ans;
}

function fromMeanVariance(mean: number, variance: number): ServiceMoments | null {
  if (!(mean > 0) || !(variance >= 0) || !Number.isFinite(mean) || !Number.isFinite(variance)) return null;
  const std = Math.sqrt(variance);
  return { mean, std, cv: std / mean, mu: 1 / mean };
}

type Values = Partial<Record<ServiceParam, number>>;

/** Momentos da distribuição, ou null se os parâmetros ainda não formam uma distribuição válida. */
export function serviceMoments(key: DistributionKey, v: Values): ServiceMoments | null {
  const { mean, k, cv, min, mode, max, loc, scale } = v;
  switch (key) {
    case "deterministic": return mean === undefined ? null : fromMeanVariance(mean, 0);
    case "exponential": return mean === undefined ? null : fromMeanVariance(mean, mean * mean);
    case "erlang":
      return mean === undefined || k === undefined || !Number.isInteger(k) || k < 1 ? null : fromMeanVariance(mean, (mean * mean) / k);
    case "lognormal":
    case "weibull":
      return mean === undefined || cv === undefined || !(cv > 0) ? null : fromMeanVariance(mean, (cv * mean) ** 2);
    case "uniform":
      return min === undefined || max === undefined || !(min >= 0) || !(max > min)
        ? null : fromMeanVariance((min + max) / 2, (max - min) ** 2 / 12);
    case "triangular":
      if (min === undefined || mode === undefined || max === undefined) return null;
      if (!(min >= 0) || !(max > min) || mode < min || mode > max) return null;
      return fromMeanVariance(
        (min + mode + max) / 3,
        (min * min + max * max + mode * mode - min * max - min * mode - mode * max) / 18,
      );
    case "truncated_normal": {
      if (loc === undefined || scale === undefined || !(scale > 0)) return null;
      const a = -loc / scale;                                   // limite inferior padronizado (truncagem em 0)
      const tail = 0.5 * erfc(a / Math.SQRT2);                  // P(Z > a)
      const pdf = Math.exp(-a * a / 2) / Math.sqrt(2 * Math.PI);
      if (!(tail > 0)) return null;
      const h = pdf / tail;
      return fromMeanVariance(loc + scale * h, scale * scale * (1 + a * h - h * h));
    }
  }
}

// ---------- formulário ----------

export type ServiceParse =
  | { ok: true; service: ServiceParams }
  | { ok: false; errors: FieldErrors };

/** Lê só os campos da distribuição escolhida. As regras de domínio ficam na API. */
export function parseService(values: FormValues): ServiceParse {
  const info = distributionInfo(values.distribution);
  const errors: FieldErrors = {};
  const out: Values = {};
  for (const f of info.fields) {
    const n = parseNumber(values[f.field]);
    if (!Number.isFinite(n)) errors[f.field] = "Informe um número.";
    else if (f.integer && !Number.isInteger(n)) errors[f.field] = "Informe um número inteiro.";
    else out[f.field] = n;
  }
  if (Object.keys(errors).length > 0) return { ok: false, errors };
  return { ok: true, service: { distribution: info.key, values: out } };
}

/** Texto de resumo do formulário: E[S], desvio, CV, μ e ρ (null se ainda não há como calcular). */
export function serviceSummary(values: FormValues): string | null {
  const parsed = parseService(values);
  if (!parsed.ok) return null;
  const m = serviceMoments(parsed.service.distribution, parsed.service.values);
  if (!m) return null;
  const lambda = parseNumber(values.lambda);
  const parts = [
    `E[S] = ${formatNumber(Number(m.mean.toPrecision(4)))} s`,
    `desvio = ${formatNumber(Number(m.std.toPrecision(4)))} s`,
    `CV = ${formatNumber(Number(m.cv.toPrecision(3)))}`,
    `μ = ${formatNumber(Number(m.mu.toPrecision(4)))} req/s`,
  ];
  if (Number.isFinite(lambda) && lambda > 0) parts.push(`ρ = ${formatNumber(Number((lambda * m.mean).toPrecision(3)))}`);
  return parts.join(" · ");
}

/** Valores do formulário para uma distribuição já numérica (usado ao reabrir do histórico). */
export function serviceToText(service: ServiceParams): Partial<Record<ServiceParam | "distribution", string>> {
  const text: Partial<Record<ServiceParam | "distribution", string>> = { distribution: service.distribution };
  for (const [name, value] of Object.entries(service.values)) {
    if (value !== undefined) text[name as ServiceParam] = String(value);
  }
  return text;
}
