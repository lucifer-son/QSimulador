import { MODELS, usesService } from "./models";
import { parseNumber } from "./request";
import { parseService, serviceMoments } from "./service";
import type { ExperimentModelKey, FormValues, MetricName, ServiceParam } from "./types";

export type SweepVariable = "lambda" | "mu" | "servers" | "capacity" | "cv" | "k";

export const VARIABLE_INFO: Record<SweepVariable, { label: string; unit: string; integer: boolean }> = {
  lambda: { label: "Chegadas λ", unit: "req/s", integer: false },
  mu: { label: "Serviço μ", unit: "req/s", integer: false },
  servers: { label: "Servidores c", unit: "", integer: true },
  capacity: { label: "Capacidade K", unit: "clientes", integer: true },
  cv: { label: "CV do serviço", unit: "", integer: false },
  k: { label: "Etapas k (Erlang)", unit: "", integer: true },
};

/** M/G/1: a variável que muda a *forma* do serviço (e portanto o CV) em cada distribuição. */
export function shapeVariable(distribution: string | undefined): "cv" | "k" | null {
  if (distribution === "erlang") return "k";
  if (distribution === "lognormal" || distribution === "weibull") return "cv";
  return null;
}

/** Carga oferecida λ/(c·μ) a partir da qual a fila já é considerada de alta utilização (convenção visual). */
export const HIGH_UTILIZATION = 0.8;

/**
 * Variáveis que o modelo permite varrer (c e K só onde existem). No M/G/1, μ muda a escala do
 * serviço e preserva o CV; cv e k (lognormal/Weibull e Erlang) variam a variabilidade.
 */
export function sweepVariables(model: ExperimentModelKey, distribution?: string): SweepVariable[] {
  if (usesService(model)) {
    const shape = shapeVariable(distribution);
    return ["lambda", "mu", ...(model === "mgc" ? (["servers"] as const) : []), ...(shape ? [shape] : [])];
  }
  const info = MODELS[model];
  return [
    "lambda", "mu",
    ...(info.usesServers ? (["servers"] as const) : []),
    ...(info.usesCapacity ? (["capacity"] as const) : []),
  ];
}

/** Fórmula da carga oferecida por servidor (λ/(c·μ); nos modelos de serviço geral, com E[S] no lugar de 1/μ). */
export const loadFormula = (model: string | undefined): string =>
  model === "mg1" ? "λ·E[S]" : model === "mgc" ? "λ·E[S]/c" : "λ/(c·μ)";

/** Métrica mostrada primeiro: o bloqueio no Erlang-B (a espera é sempre zero), o tempo no sistema nos demais. */
export const defaultMetric = (model: string | undefined): MetricName => (model === "erlangb" ? "p_block" : "W");

/** Textos da análise de sensibilidade: o que varia em cada modelo. */
export function sensitivityTexts(model: ExperimentModelKey): { label: string; hint: string; effect: (delta: string) => string } {
  if (usesService(model)) {
    const unit = model === "mgc" ? "c e o k do Erlang variam ±1" : "o k do Erlang varia ±1";
    return {
      label: "Variação de λ, μ e CV (%)",
      hint: `De 0 a 50. ${model === "mgc" ? "c e o k do Erlang variam ±1." : "O k do Erlang varia ±1."}`,
      effect: (d) => `λ, μ e o CV variam ±${d}%; ${unit} unidade.`,
    };
  }
  const integers = model === "erlangb" ? "c varia" : "c e K variam";
  return {
    label: "Variação de λ e μ (%)",
    hint: `De 0 a 50. ${integers} ±1.`,
    effect: (d) => `λ e μ variam ±${d}%; ${integers} ±1 unidade.`,
  };
}

/** Valores do sistema como estão digitados no Laboratório (o serviço só existe no M/G/1). */
export type SystemText = { lambda: string; mu: string; servers: string; capacity: string }
  & Partial<Record<"distribution" | ServiceParam, string>>;
export interface RangeText { start: string; end: string; step: string }
export interface SimText { simulationTime: string; replications: string; warmupTime: string; seed: string }

export type ExpErrors = Record<string, string>;
export type Built<T> = { ok: true; body: T } | { ok: false; errors: ExpErrors };
type Json = number | boolean | string | number[] | Record<string, number | string>;
export type Body = Record<string, Json | Record<string, number | string>[]>;

export { reader };

const NUMBER_ERROR = "Informe um número.";
const INTEGER_ERROR = "Informe um número inteiro.";

function reader(errors: ExpErrors) {
  return (key: string, text: string, integer = false): number => {
    const n = parseNumber(text);
    if (!Number.isFinite(n)) errors[key] = NUMBER_ERROR;
    else if (integer && !Number.isInteger(n)) errors[key] = INTEGER_ERROR;
    else return n;
    return NaN;
  };
}

/** Texto compacto de um número para campos de formulário (sem agrupamento de milhar). */
export function toText(value: number): string {
  return String(Number(value.toPrecision(4)));
}

function numberOr(text: string, fallback: number): number {
  const n = parseNumber(text);
  return Number.isFinite(n) && n > 0 ? n : fallback;
}

const BLANK_SERVICE: Record<"distribution" | ServiceParam, string> = {
  distribution: "lognormal", mean: "", k: "", cv: "", min: "", mode: "", max: "", loc: "", scale: "",
};

export type ServiceBody = Record<string, number | string>;

/** O serviço digitado no Laboratório, no formato da API; null se os campos ainda não são números. */
export function readServiceBody(system: SystemText): ServiceBody | null {
  const parsed = parseService({ ...BLANK_SERVICE, ...system } as unknown as FormValues);
  return parsed.ok ? { distribution: parsed.service.distribution, ...parsed.service.values } : null;
}

/** Média, desvio e CV do serviço do Laboratório (null se os campos não formam uma distribuição). */
export function serviceMomentsOf(system: SystemText) {
  const parsed = parseService({ ...BLANK_SERVICE, ...system } as unknown as FormValues);
  return parsed.ok ? serviceMoments(parsed.service.distribution, parsed.service.values) : null;
}

const SERVICE_ERROR = "Complete os campos do serviço no Laboratório.";

/** Faixas sugeridas para M/G/1 e M/G/c (a taxa de serviço vem de 1/E[S], não do campo μ). */
function suggestServiceRange(variable: SweepVariable, model: ExperimentModelKey, system: SystemText): RangeText {
  const mean = serviceMomentsOf(system)?.mean ?? 0.02;
  const lambda = numberOr(system.lambda ?? "", 1);
  const servers = model === "mgc" ? Math.max(1, Math.round(numberOr(system.servers ?? "", 1))) : 1;
  const text = (start: number, end: number, step: number): RangeText =>
    ({ start: toText(start), end: toText(end), step: toText(step) });
  switch (variable) {
    case "lambda": {
      const total = servers / mean;       // capacidade de atendimento: onde a fila satura
      return text(total / 10, total * 1.2, total / 10);   // até além da saturação
    }
    case "mu": {
      const needed = lambda / servers;    // μ mínimo para a fila ser estável
      return text(needed * 0.5, needed * 2, needed / 10);
    }
    case "servers": return text(1, Math.min(30, Math.max(2, Math.ceil(2 * lambda * mean))), 1);
    case "cv": return text(0.25, 3, 0.25);
    case "k": return text(1, 8, 1);
    default: return text(1, 10, 1);
  }
}

/** Faixa sugerida para varrer `variable` em torno do sistema do Laboratório. */
export function suggestRange(variable: SweepVariable, model: ExperimentModelKey, system: SystemText): RangeText {
  if (usesService(model)) return suggestServiceRange(variable, model, system);
  const lambda = numberOr(system.lambda, 1);
  const mu = numberOr(system.mu, 1);
  const servers = MODELS[model].usesServers ? Math.max(1, Math.round(numberOr(system.servers, 1))) : 1;
  const capacity = Math.round(numberOr(system.capacity, 10));
  const text = (start: number, end: number, step: number): RangeText =>
    ({ start: toText(start), end: toText(end), step: toText(step) });

  switch (variable) {
    case "lambda": {
      const total = servers * mu;               // capacidade de atendimento: onde a fila ilimitada satura
      // No Erlang-B não há saturação: a faixa vai bem além de c·μ, onde o bloqueio fica alto.
      return text(total / 10, total * (model === "erlangb" ? 1.6 : 1.2), total / 10);
    }
    case "mu": {
      const needed = lambda / servers;          // μ mínimo para a fila ilimitada ser estável
      return text(needed * 0.5, needed * 2, needed / 10);
    }
    case "servers": {
      const end = Math.min(30, Math.max(2, Math.ceil((2 * lambda) / mu)));
      return text(1, end, 1);
    }
    case "capacity": {
      const end = Math.max(servers + 4, 2 * capacity);
      return text(servers, end, Math.max(1, Math.ceil((end - servers) / 12)));
    }
    default:    // cv e k só existem no M/G/1 (tratado acima)
      return text(1, 5, 1);
  }
}

/** Lista de servidores sugerida para comparar: o c do Laboratório e seus vizinhos. */
export function suggestServers(model: ExperimentModelKey, system: SystemText): string {
  const c = MODELS[model].usesServers ? Math.max(1, Math.round(numberOr(system.servers, 1))) : 1;
  return [c - 1, c, c + 1].filter((n) => n >= 1).join(", ");
}

export function readSystem(
  model: ExperimentModelKey, system: SystemText, skip: SweepVariable | null, errors: ExpErrors,
): Body {
  const read = reader(errors);
  const info = MODELS[model];
  const body: Body = {};
  if (skip !== "lambda") body.lambda = read("lambda", system.lambda);
  if (usesService(model)) {
    // O serviço (distribuição e parâmetros) vai junto, mesmo quando a variável varrida é uma delas.
    const service = readServiceBody(system);
    if (service) body.service = service;
    else errors.service = SERVICE_ERROR;
    if (model === "mgc" && skip !== "servers") body.servers = read("servers", system.servers, true);
    return body;
  }
  if (skip !== "mu") body.mu = read("mu", system.mu);
  if (info.usesServers && skip !== "servers") body.servers = read("servers", system.servers, true);
  if (info.usesCapacity && skip !== "capacity") body.capacity = read("capacity", system.capacity, true);
  return body;
}

function readRange(range: RangeText, integer: boolean, errors: ExpErrors): Body {
  const read = reader(errors);
  return {
    start: read("start", range.start, integer),
    end: read("end", range.end, integer),
    step: read("step", range.step, integer),
  };
}

export interface SweepSimulationText extends SimText { enabled: boolean }

/** Corpo do POST /api/experiments/sweep. Só confere o formato; as regras ficam na API. */
export function buildSweepBody(
  model: ExperimentModelKey, variable: SweepVariable, system: SystemText, range: RangeText, sim: SweepSimulationText,
): Built<Body> {
  const errors: ExpErrors = {};
  const read = reader(errors);
  const body: Body = {
    model, variable,
    ...readSystem(model, system, variable, errors),
    ...readRange(range, VARIABLE_INFO[variable].integer, errors),
  };
  if (sim.enabled) {
    body.simulate = true;
    body.simulation_time = read("simulationTime", sim.simulationTime);
    body.replications = read("replications", sim.replications, true);
    body.warmup_time = read("warmupTime", sim.warmupTime);
    if (sim.seed.trim() !== "") body.seed = read("seed", sim.seed, true);
  }
  return Object.keys(errors).length > 0 ? { ok: false, errors } : { ok: true, body };
}

/** Converte "1, 2 4;8" em [1, 2, 4, 8]; null se algum item não for inteiro. */
export function parseServerList(text: string): number[] | null {
  const items = text.split(/[\s,;]+/).filter((s) => s !== "");
  if (items.length === 0) return null;
  const values = items.map(parseNumber);
  return values.every(Number.isInteger) ? values : null;
}

/**
 * Corpo do POST /api/experiments/servers: compara M/M/c (ou M/M/c/K se o modelo tem capacidade),
 * o Erlang-B (K = c em cada série) ou o M/G/c (com o serviço do Laboratório).
 */
export function buildServersBody(
  model: ExperimentModelKey, system: SystemText, serversText: string, range: RangeText,
): Built<Body> {
  const errors: ExpErrors = {};
  const read = reader(errors);
  const list = parseServerList(serversText);
  if (list === null) errors.serversList = "Informe números inteiros separados por vírgula.";
  const body: Body = { servers_list: list ?? [] };
  if (model === "mgc") {
    body.model = "mgc";
    const service = readServiceBody(system);
    if (service) body.service = service;
    else errors.service = SERVICE_ERROR;
  } else {
    if (model === "erlangb") body.model = "erlangb";
    body.mu = read("mu", system.mu);
    if (MODELS[model].usesCapacity) body.capacity = read("capacity", system.capacity, true);
  }
  Object.assign(body, readRange(range, false, errors));
  return Object.keys(errors).length > 0 ? { ok: false, errors } : { ok: true, body };
}

/** Corpo do POST /api/experiments/sensitivity. */
export function buildSensitivityBody(
  model: ExperimentModelKey, system: SystemText, deltaText: string,
): Built<Body> {
  const errors: ExpErrors = {};
  const read = reader(errors);
  const body: Body = {
    model,
    ...readSystem(model, system, null, errors),
    delta_pct: read("delta", deltaText),
  };
  return Object.keys(errors).length > 0 ? { ok: false, errors } : { ok: true, body };
}

// ---------- comparação de distribuições (M/G/1) ----------

export interface ServicePreset {
  key: string;
  label: string;
  /** Distribuição com a média `mean` (o CV é o que muda entre as opções). */
  make: (mean: number) => ServiceBody;
}

/** Opções com o mesmo E[S] do Laboratório: só a variabilidade muda. */
export const SERVICE_PRESETS: ServicePreset[] = [
  { key: "deterministic", label: "Determinística (CV 0)", make: (m) => ({ distribution: "deterministic", mean: m }) },
  { key: "erlang4", label: "Erlang-4 (CV 0,5)", make: (m) => ({ distribution: "erlang", mean: m, k: 4 }) },
  { key: "exponential", label: "Exponencial (CV 1)", make: (m) => ({ distribution: "exponential", mean: m }) },
  { key: "lognormal15", label: "Lognormal (CV 1,5)", make: (m) => ({ distribution: "lognormal", mean: m, cv: 1.5 }) },
  { key: "lognormal2", label: "Lognormal (CV 2)", make: (m) => ({ distribution: "lognormal", mean: m, cv: 2 }) },
];
export const LAB_SERVICE_KEY = "lab";
export const DEFAULT_SERVICE_CHOICES = [LAB_SERVICE_KEY, "deterministic", "exponential"];
export const MAX_COMPARED_SERVICES = 8;

/** Corpo do POST /api/experiments/services: as opções marcadas (e o serviço do Laboratório, se marcado). */
export function buildServicesBody(
  system: SystemText, chosen: string[], range: RangeText, model: "mg1" | "mgc" = "mg1",
): Built<Body> {
  const errors: ExpErrors = {};
  const services: ServiceBody[] = [];
  const moments = serviceMomentsOf(system);
  if (chosen.length < 2 || chosen.length > MAX_COMPARED_SERVICES) {
    errors.services = `Escolha de 2 a ${MAX_COMPARED_SERVICES} distribuições.`;
  }
  if (chosen.includes(LAB_SERVICE_KEY)) {
    const lab = readServiceBody(system);
    if (lab) services.push(lab);
    else errors.service = SERVICE_ERROR;
  }
  const others = SERVICE_PRESETS.filter((p) => chosen.includes(p.key));
  if (others.length > 0) {
    if (moments) services.push(...others.map((p) => p.make(Number(moments.mean.toPrecision(12)))));
    else errors.service = SERVICE_ERROR;
  }
  const body: Body = { services, ...readRange(range, false, errors) };
  if (model === "mgc") {            // c fixo da comparação (com c = 1 o resultado é o do M/G/1)
    body.model = "mgc";
    body.servers = reader(errors)("servers", system.servers ?? "", true);
  }
  return Object.keys(errors).length > 0 ? { ok: false, errors } : { ok: true, body };
}

/** Campo da API -> campo do formulário de experimentos (o que não está aqui só aparece na mensagem). */
const API_TO_EXP: Record<string, string> = {
  start: "start", end: "end", step: "step", servers_list: "serversList", delta_pct: "delta",
  service: "service", services: "services",
  t: "t", target: "target", target_blocking: "blocking", server_cost: "serverCost", wait_cost: "waitCost",
  loss_cost: "lossCost", c_min: "cMin", c_max: "cMax",
  lambda: "lambda", mu: "mu", servers: "servers", capacity: "capacity",
  simulation_time: "simulationTime", replications: "replications", warmup_time: "warmupTime", seed: "seed",
};

export function experimentFieldErrors(
  fields: { field: string; message: string }[] | undefined, code: string,
): ExpErrors {
  const out: ExpErrors = {};
  for (const issue of fields ?? []) {
    const key = API_TO_EXP[issue.field];
    if (!key) continue;
    out[key] = code === "invalid_request" ? "Valor inválido para este campo." : issue.message;
  }
  return out;
}
