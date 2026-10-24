/**
 * Comparação de cenários (Fase 12): o formulário de cenários, o corpo do pedido e a leitura do resultado.
 *
 * Cada campo de um cenário aceita um valor absoluto ("12") ou uma variação em relação à base:
 * em λ, μ e CV, percentual com "%" ("+20%", "-10%"); em c, K e k, unidades com sinal ("+1", "-1").
 * Campo vazio = como na base. As regras de verdade (limites, estabilidade) ficam na API.
 */
import type { ScenarioMetric, ScenarioRow, ScenariosResult } from "../api/scenarios";
import { estimateCost } from "./estimate";
import { readSystem, type Body, type Built, type ExpErrors, type SimText, type SystemText } from "./experiments";
import { formatCompactCount } from "./format";
import { MODELS, usesService } from "./models";
import { parseNumber } from "./number";
import type { ExperimentModelKey, MetricName } from "./types";

export const MAX_SCENARIOS = 10;

export type VariableKey = "lambda" | "mu" | "servers" | "capacity" | "cv" | "k";
export const INTEGER_VARIABLES: VariableKey[] = ["servers", "capacity", "k"];

/** Campos de um cenário como digitados. `id` é estável (a chave da lista e dos erros), não a posição. */
export interface ScenarioText extends Record<VariableKey, string> {
  id: number;
  name: string;
  model: "" | ExperimentModelKey;     // vazio = o modelo da base
}

export const VARIABLE_LABEL: Record<VariableKey, string> = {
  lambda: "λ", mu: "μ", servers: "c (servidores)", capacity: "K (capacidade)", cv: "CV do serviço", k: "k (etapas Erlang)",
};

export function blankScenario(id: number, name = ""): ScenarioText {
  return { id, name, model: "", lambda: "", mu: "", servers: "", capacity: "", cv: "", k: "" };
}

/** Dois cenários de partida (o aumento de carga e a capacidade), para a tela abrir com algo útil. */
export function initialScenarios(model: ExperimentModelKey): ScenarioText[] {
  const capacity = MODELS[model].usesServers
    ? { ...blankScenario(2, "+1 servidor"), servers: "+1" }
    : { ...blankScenario(2, "μ +20%"), mu: "+20%" };
  return [{ ...blankScenario(1, "+20% de λ"), lambda: "+20%" }, capacity];
}

/** Variáveis que o cenário pode alterar, conforme o modelo efetivo (o do cenário, ou o da base). */
export function visibleVariables(base: ExperimentModelKey, scenario: ScenarioText): VariableKey[] {
  const model = scenario.model || base;
  const info = MODELS[model];
  return [
    "lambda", "mu",
    ...(info.usesServers ? (["servers"] as const) : []),
    ...(info.usesCapacity ? (["capacity"] as const) : []),
    ...(usesService(model) ? (["cv", "k"] as const) : []),
  ];
}

// ---------- leitura dos campos ----------

export interface OverrideBody { mode: "absolute" | "relative"; value: number }
type Parsed = { ok: true; override: OverrideBody | null } | { ok: false; error: string };

const SHAPE = /^([+\-−])?\s*([0-9.,eE+-]+?)\s*(%)?$/;

export function parseOverride(text: string, integer: boolean): Parsed {
  const t = text.trim();
  if (t === "") return { ok: true, override: null };
  const match = SHAPE.exec(t);
  const number = match ? parseNumber(match[2]) : NaN;
  if (!match || !Number.isFinite(number) || number < 0) return { ok: false, error: "Use um valor (12), +1 / −1 ou uma variação em % (+20%)." };
  const [, sign, , percent] = match;
  const signed = sign === "-" || sign === "−" ? -number : number;
  if (integer) {
    if (percent) return { ok: false, error: "Este valor é inteiro: use +1 ou −1 (unidades), ou o valor absoluto." };
    if (!Number.isInteger(signed)) return { ok: false, error: "Informe um número inteiro." };
    return { ok: true, override: { mode: sign ? "relative" : "absolute", value: signed } };
  }
  if (percent) return { ok: true, override: { mode: "relative", value: signed } };
  if (sign) return { ok: false, error: "Para variar em relação à base use %, ex.: +20%. Sem %, digite o valor absoluto." };
  return { ok: true, override: { mode: "absolute", value: number } };
}

export const fieldKey = (id: number, variable: VariableKey | "model" | "name" | "service"): string => `s${id}.${variable}`;

const BODY_NAME: Record<VariableKey, string> = {
  lambda: "lambda", mu: "mu", servers: "servers", capacity: "capacity", cv: "cv", k: "k",
};

/** Corpo do POST /api/scenarios/compare, com a base do Laboratório e a simulação dele. */
export function buildScenariosBody(
  model: ExperimentModelKey, system: SystemText, sim: SimText, scenarios: ScenarioText[], bonferroni: boolean,
): Built<Body> {
  const errors: ExpErrors = {};
  const base = { model, ...readSystem(model, system, null, errors) };

  const out: Record<string, unknown>[] = scenarios.map((s) => {
    const item: Record<string, unknown> = {};
    if (s.name.trim()) item.name = s.name.trim();
    if (s.model) item.model = s.model;
    for (const variable of visibleVariables(model, s)) {
      const parsed = parseOverride(s[variable], INTEGER_VARIABLES.includes(variable));
      if (!parsed.ok) errors[fieldKey(s.id, variable)] = parsed.error;
      else if (parsed.override) item[BODY_NAME[variable]] = parsed.override;
    }
    return item;
  });
  if (scenarios.length === 0) errors.scenarios = "Adicione pelo menos um cenário.";

  const body: Record<string, unknown> = { base, scenarios: out, bonferroni };
  const number = (key: string, text: string, integer = false): number => {
    const n = parseNumber(text);
    if (!Number.isFinite(n)) errors[key] = "Informe um número.";
    else if (integer && !Number.isInteger(n)) errors[key] = "Informe um número inteiro.";
    return n;
  };
  body.simulation_time = number("simulationTime", sim.simulationTime);
  body.replications = number("replications", sim.replications, true);
  body.warmup_time = number("warmupTime", sim.warmupTime);
  if (sim.seed.trim() !== "") body.seed = number("seed", sim.seed, true);

  return Object.keys(errors).length > 0 ? { ok: false, errors } : { ok: true, body: body as Body };
}

/** Chegadas esperadas somando a base e os cenários (λ resolvido só pelo override de λ; ρ não é conferido aqui). */
export function estimateScenariosText(system: SystemText, scenarios: ScenarioText[], sim: SimText): string | null {
  const lambda = parseNumber(system.lambda);
  if (!Number.isFinite(lambda)) return null;
  const rates = [lambda, ...scenarios.map((s) => {
    const parsed = parseOverride(s.lambda, false);
    if (!parsed.ok || !parsed.override) return lambda;
    return parsed.override.mode === "relative" ? lambda * (1 + parsed.override.value / 100) : parsed.override.value;
  })];
  const time = parseNumber(sim.simulationTime);
  const reps = parseNumber(sim.replications);
  const cost = estimateCost(rates.reduce((a, b) => a + b, 0), time, reps);
  if (!cost) return null;
  const seconds = cost.seconds;
  const duration = seconds < 1 ? "menos de 1 s" : seconds < 60 ? `cerca de ${Math.round(seconds)} s` : `cerca de ${Math.round(seconds / 60)} min`;
  return `${formatCompactCount(cost.arrivals)} chegadas no total (${rates.length} simulações), ${duration}`;
}

// ---------- erros da API ----------

export interface ScenarioErrors { fields: ExpErrors; general: string[] }

const SIM_FIELD: Record<string, string> = {
  simulation_time: "simulationTime", replications: "replications", warmup_time: "warmupTime", seed: "seed",
};

/** Leva os campos do 422 (scenarios[2].cv, base.lambda, replications...) para os campos da tela. */
export function scenarioFieldErrors(
  issues: { field: string; message: string }[] | undefined, code: string, scenarios: ScenarioText[],
): ScenarioErrors {
  const fields: ExpErrors = {};
  const general: string[] = [];
  for (const issue of issues ?? []) {
    const message = code === "invalid_request" ? "Valor inválido para este campo." : issue.message;
    const item = /^scenarios\[(\d+)\]\.(\w+)$/.exec(issue.field);
    if (item) {
      const scenario = scenarios[Number(item[1])];
      const variable = item[2] === "lambda" ? "lambda" : item[2];
      if (scenario) {
        fields[fieldKey(scenario.id, variable as VariableKey)] = message;
        continue;
      }
    }
    if (SIM_FIELD[issue.field]) fields[SIM_FIELD[issue.field]] = message;
    else if (issue.field.startsWith("base.")) general.push(`Base (Laboratório): ${message}`);
    else general.push(message);
  }
  return { fields, general };
}

// ---------- leitura do resultado ----------

export const METRIC_ORDER: MetricName[] = ["rho", "L", "Lq", "W", "Wq", "p0", "throughput", "p_wait", "p_block"];

/** Métricas que aparecem em algum cenário (ou na base), na ordem canônica. */
export function metricsOf(result: { base: ScenarioRow | null; scenarios: ScenarioRow[] }): MetricName[] {
  const present = new Set<string>();
  for (const row of [result.base, ...result.scenarios]) if (row) Object.keys(row.metrics).forEach((m) => present.add(m));
  return METRIC_ORDER.filter((m) => present.has(m));
}

export const VERDICT_LABEL = {
  higher: "Aumento significativo ↑", lower: "Redução significativa ↓", inconclusive: "Inconclusivo",
} as const;

const fixed = (digits: number) => new Intl.NumberFormat("pt-BR", { minimumFractionDigits: digits, maximumFractionDigits: digits });

/** Diferença com sinal (a de frações é em pontos percentuais). Zero arredondado fica sem sinal. */
export function formatDelta(name: MetricName, value: number): string {
  const percent = name === "rho" || name === "p0" || name === "p_wait" || name === "p_block";
  const body = percent ? `${fixed(2).format(Math.abs(value) * 100)} p.p.` : new Intl.NumberFormat("pt-BR", { maximumSignificantDigits: 4 }).format(Math.abs(value));
  const zero = Number(percent ? (Math.abs(value) * 100).toFixed(2) : Math.abs(value).toPrecision(4)) === 0;
  return `${zero ? "" : value > 0 ? "+" : "−"}${body}`;
}

export const formatRelative = (value: number | null | undefined): string =>
  value === null || value === undefined ? "—"
    : `${Number(Math.abs(value * 100).toFixed(1)) === 0 ? "" : value > 0 ? "+" : "−"}${fixed(1).format(Math.abs(value) * 100)}%`;

/** "λ 8 → 9,6; c 10 → 11": o que o cenário muda na base, já resolvido pela API. */
export function describeChanges(row: ScenarioRow): string {
  if (row.changes.length === 0) return "igual à base";
  const name: Record<string, string> = {
    model: "modelo", lambda: "λ", mu: "μ", servers: "c", capacity: "K", distribution: "serviço", cv: "CV", k: "k",
  };
  const shown = (v: unknown) => (typeof v === "number" ? new Intl.NumberFormat("pt-BR", { maximumSignificantDigits: 5 }).format(v) : v === null || v === undefined ? "—" : String(v));
  return row.changes.map((c) => `${name[c.field] ?? c.field} ${shown(c.from_value)} → ${shown(c.to_value)}`).join("; ");
}

export const metricOf = (row: ScenarioRow, name: MetricName): ScenarioMetric | undefined => row.metrics[name];

/** Linhas com diferença pareada para a métrica (as que entram no gráfico). */
export function rowsWithDiff(result: Pick<ScenariosResult, "scenarios">, name: MetricName): ScenarioRow[] {
  return result.scenarios.filter((r) => r.metrics[name]?.diff);
}
