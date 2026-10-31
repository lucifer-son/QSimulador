/**
 * Cruzamento semaforizado (Fase 13.1): o formulário, o corpo dos pedidos e a leitura dos erros da API.
 *
 * Na tela, as taxas de chegada são em veículos por minuto (como se conta no vídeo) e os tempos em segundos;
 * a API trabalha em veículos por segundo. Os parâmetros que vêm da medição no vídeo (ℓ, amarelo utilizável,
 * fila inicial, offset) começam vazios: vazio = "não informado", e a API avisa que assumiu 0.
 */
import type {
  ApproachKey, Phase, Scope, Summary, SuggestedBody, TrafficAlert, VideoEstimate,
} from "../api/traffic";
import { parseNumber } from "./number";

export const MAX_PLANS = 10;
export const MAX_SWEEP_POINTS = 40;

export type HeadwayDistribution = "deterministic" | "exponential" | "lognormal" | "weibull" | "erlang";
export const HEADWAY_LABEL: Record<HeadwayDistribution, string> = {
  deterministic: "Determinístico", exponential: "Exponencial", lognormal: "Lognormal", weibull: "Weibull", erlang: "Erlang-k",
};
export const HEADWAY_ORDER: HeadwayDistribution[] = ["deterministic", "lognormal", "weibull", "erlang", "exponential"];

export interface ProfileBlockText { duration: string; rate: string }   // duração em s e taxa em veículos/min

export interface ApproachText {
  name: string;
  rate: string;                       // veículos/min (constante); ignorada se houver `profile`
  profile: ProfileBlockText[] | null; // perfil por blocos vindo do vídeo
  distribution: HeadwayDistribution;
  headwayMean: string;                // s
  headwayCv: string;
  headwayK: string;
  firstVehicle: string;               // ℓ (s)
  amberUsable: string;                // s
  initialQueue: string;               // veículos
}

export interface TrafficText {
  green1: string; amber1: string; allRed1: string;
  green2: string; amber2: string; allRed2: string;
  offset: string;
  approaches: [ApproachText, ApproachText];
  simulationTime: string; replications: string; warmupTime: string; seed: string; seriesStep: string;
}

export interface PlanText { id: number; name: string; green1: string; green2: string; amber1: string; amber2: string; allRed1: string; allRed2: string }
export interface SweepText { minGreen1: string; minGreen2: string; step: string }

export const blankApproach = (name: string): ApproachText => ({
  name, rate: "", profile: null, distribution: "lognormal", headwayMean: "", headwayCv: "", headwayK: "",
  firstVehicle: "", amberUsable: "", initialQueue: "",
});

export function blankTraffic(): TrafficText {
  return {
    green1: "", amber1: "", allRed1: "", green2: "", amber2: "", allRed2: "", offset: "",
    approaches: [blankApproach("Aproximação 1"), blankApproach("Aproximação 2")],
    simulationTime: "3600", replications: "20", warmupTime: "0", seed: "2026", seriesStep: "",
  };
}

/** Valores HIPOTÉTICOS para conhecer a tela. Não são medições de nenhum cruzamento real. */
export function exampleTraffic(): TrafficText {
  return {
    ...blankTraffic(),
    green1: "30", amber1: "3", allRed1: "2", green2: "25", amber2: "3", allRed2: "2", offset: "0",
    approaches: [
      { ...blankApproach("Aproximação 1"), rate: "12", distribution: "lognormal", headwayMean: "2", headwayCv: "0.3", firstVehicle: "2.4", amberUsable: "1", initialQueue: "0" },
      { ...blankApproach("Aproximação 2"), rate: "9.6", distribution: "lognormal", headwayMean: "2", headwayCv: "0.3", firstVehicle: "2.4", amberUsable: "1", initialQueue: "0" },
    ],
  };
}

export const blankPlan = (id: number, name = ""): PlanText => ({
  id, name, green1: "", green2: "", amber1: "", amber2: "", allRed1: "", allRed2: "",
});

export const blankSweep = (): SweepText => ({ minGreen1: "", minGreen2: "", step: "5" });

// ---------- leitura dos campos ----------

export type TrafficErrors = Record<string, string>;
type Body = Record<string, unknown>;
export type Built = { ok: true; body: Body } | { ok: false; errors: TrafficErrors };

const trimmed = (s: string) => s.trim();

class Reader {
  errors: TrafficErrors = {};
  num(key: string, text: string, label: string, opts: { required?: boolean; min?: number; positive?: boolean; integer?: boolean } = {}): number | null | undefined {
    const t = trimmed(text);
    if (t === "") {
      if (opts.required) this.errors[key] = `Informe ${label}.`;
      return opts.required ? undefined : null;
    }
    const v = parseNumber(t);
    if (!Number.isFinite(v)) { this.errors[key] = `${label}: digite um número.`; return undefined; }
    if (opts.integer && !Number.isInteger(v)) { this.errors[key] = `${label}: use um número inteiro.`; return undefined; }
    if (opts.positive && v <= 0) { this.errors[key] = `${label}: deve ser maior que zero.`; return undefined; }
    if (!opts.positive && v < (opts.min ?? 0)) { this.errors[key] = `${label}: não pode ser negativo.`; return undefined; }
    return v;
  }
}

const PHASE_KEYS = [
  { green: "green1", amber: "amber1", allRed: "allRed1" },
  { green: "green2", amber: "amber2", allRed: "allRed2" },
] as const;

function readPhases(r: Reader, form: Pick<TrafficText, "green1" | "amber1" | "allRed1" | "green2" | "amber2" | "allRed2">) {
  return PHASE_KEYS.map((k, i) => ({
    green: r.num(k.green, form[k.green], `o verde da fase ${i + 1}`, { required: true, positive: true }),
    amber: r.num(k.amber, form[k.amber], `o amarelo da fase ${i + 1}`) ?? 0,
    all_red: r.num(k.allRed, form[k.allRed], `o todo-vermelho da fase ${i + 1}`) ?? 0,
  }));
}

function readApproach(r: Reader, a: ApproachText, i: number) {
  const p = `a${i + 1}.`;
  const n = i + 1;
  const approach: Body = { name: trimmed(a.name) || `Aproximação ${n}` };
  if (a.profile) {
    approach.profile = a.profile.map((b, j) => ({
      duration: r.num(`${p}profile.${j}`, b.duration, `a duração do bloco ${j + 1}`, { required: true, positive: true }),
      lambda: (r.num(`${p}profile.${j}`, b.rate, `a taxa do bloco ${j + 1}`, { required: true }) ?? 0) / 60,
    }));
  } else {
    const perMin = r.num(`${p}rate`, a.rate, `a chegada da aproximação ${n} (veíc./min)`, { required: true, positive: true });
    approach.lambda = perMin === undefined || perMin === null ? undefined : perMin / 60;
  }
  const mean = r.num(`${p}headwayMean`, a.headwayMean, `o intervalo médio entre veículos da aproximação ${n}`, { required: true, positive: true });
  const headway: Body = { distribution: a.distribution, mean };
  if (a.distribution === "lognormal" || a.distribution === "weibull") {
    headway.cv = r.num(`${p}headwayCv`, a.headwayCv, `o CV do intervalo da aproximação ${n}`, { required: true, positive: true });
  }
  if (a.distribution === "erlang") {
    headway.k = r.num(`${p}headwayK`, a.headwayK, `o k do Erlang da aproximação ${n}`, { required: true, positive: true, integer: true });
  }
  approach.headway = headway;
  approach.first_vehicle_time = r.num(`${p}firstVehicle`, a.firstVehicle, `o tempo do 1º veículo da aproximação ${n}`);
  approach.amber_usable = r.num(`${p}amberUsable`, a.amberUsable, `o amarelo utilizável da aproximação ${n}`);
  approach.initial_queue = r.num(`${p}initialQueue`, a.initialQueue, `a fila inicial da aproximação ${n}`, { integer: true });
  return approach;
}

function readRun(r: Reader, f: TrafficText) {
  return {
    simulation_time: r.num("simulationTime", f.simulationTime, "o tempo simulado T", { required: true, positive: true }),
    replications: r.num("replications", f.replications, "o número de réplicas", { required: true, integer: true, positive: true }),
    warmup_time: r.num("warmupTime", f.warmupTime, "o aquecimento") ?? 0,
    seed: r.num("seed", f.seed, "a semente", { integer: true }) ?? undefined,
    confidence_level: 0.95,
  };
}

/** Corpo comum às rotas do cruzamento (plano, aproximações e simulação), sem os campos extras de cada modo. */
export function buildTrafficBody(f: TrafficText): Built {
  const r = new Reader();
  const body: Body = {
    phases: readPhases(r, f),
    offset: r.num("offset", f.offset, "o offset"),
    approaches: f.approaches.map((a, i) => readApproach(r, a, i)),
    ...readRun(r, f),
  };
  const step = r.num("seriesStep", f.seriesStep, "o passo da série", { positive: true });
  if (step !== null && step !== undefined) body.series_step = step;
  return Object.keys(r.errors).length ? { ok: false, errors: r.errors } : { ok: true, body };
}

export function buildComparisonBody(f: TrafficText, plans: PlanText[], bonferroni: boolean): Built {
  const base = buildTrafficBody(f);
  const errors: TrafficErrors = base.ok ? {} : { ...base.errors };
  if (plans.length === 0) errors.plans = "Adicione ao menos um plano.";
  const r = new Reader();
  const scenarios = plans.map((p) => {
    const patch = (key: string, text: string, label: string) => {
      const v = r.num(`plan.${p.id}.${key}`, text, label, { positive: key.startsWith("green") });
      return v === null || v === undefined ? undefined : v;
    };
    const phase = (n: 1 | 2) => {
      const g = patch(`green${n}`, p[`green${n}`], `o verde da fase ${n}`);
      const y = patch(`amber${n}`, p[`amber${n}`], `o amarelo da fase ${n}`);
      const a = patch(`allRed${n}`, p[`allRed${n}`], `o todo-vermelho da fase ${n}`);
      return g === undefined && y === undefined && a === undefined ? null : { green: g, amber: y, all_red: a };
    };
    const phases = [phase(1), phase(2)];
    if (phases.every((x) => x === null)) r.errors[`plan.${p.id}.green1`] = "Troque ao menos um tempo do plano.";
    return { name: trimmed(p.name) || undefined, phases };
  });
  Object.assign(errors, r.errors);
  if (Object.keys(errors).length || !base.ok) return { ok: false, errors };
  return { ok: true, body: { ...base.body, scenarios, bonferroni } };
}

export function buildSweepBody(f: TrafficText, s: SweepText): Built {
  const base = buildTrafficBody(f);
  const r = new Reader();
  const g1 = r.num("minGreen1", s.minGreen1, "o verde mínimo da fase 1", { required: true, positive: true });
  const g2 = r.num("minGreen2", s.minGreen2, "o verde mínimo da fase 2", { required: true, positive: true });
  const step = r.num("step", s.step, "o passo da varredura", { required: true, positive: true });
  const errors = { ...(base.ok ? {} : base.errors), ...r.errors };
  if (Object.keys(errors).length || !base.ok) return { ok: false, errors };
  return { ok: true, body: { ...base.body, min_green: [g1, g2], step } };
}

// ---------- erros da API → campos do formulário ----------

const APPROACH_FIELD: Record<string, string> = {
  lambda: "rate", profile: "rate", first_vehicle_time: "firstVehicle", amber_usable: "amberUsable",
  initial_queue: "initialQueue", "headway.mean": "headwayMean", "headway.cv": "headwayCv", "headway.k": "headwayK",
  headway: "headwayMean", "headway.distribution": "headwayMean",
};
const PHASE_FIELD: Record<string, "green" | "amber" | "allRed"> = { green: "green", amber: "amber", all_red: "allRed" };
const RUN_FIELD: Record<string, string> = {
  simulation_time: "simulationTime", replications: "replications", warmup_time: "warmupTime", seed: "seed",
  series_step: "seriesStep", offset: "offset", step: "step", min_green: "minGreen1", scenarios: "plans", phases: "green1",
};

/** "approaches.1.headway.cv" → "a2.headwayCv"; "scenarios.0.phases.1.green" → "plan:0.green2". `planIds` traduz a posição em id. */
export function trafficFieldKey(field: string, planIds: number[] = []): string {
  const parts = field.split(".");
  if (parts[0] === "approaches" && parts.length >= 3) {
    const rest = parts.slice(2).join(".");
    return `a${Number(parts[1]) + 1}.${APPROACH_FIELD[rest] ?? "rate"}`;
  }
  if (parts[0] === "phases" && parts.length === 3) {
    return `${PHASE_FIELD[parts[2]] ?? "green"}${Number(parts[1]) + 1}`;
  }
  if (parts[0] === "scenarios" && parts[2] === "phases" && parts.length === 5) {
    const id = planIds[Number(parts[1])] ?? Number(parts[1]);
    return `plan.${id}.${PHASE_FIELD[parts[4]] ?? "green"}${Number(parts[3]) + 1}`;
  }
  return RUN_FIELD[field] ?? field;
}

export function trafficErrors(fields: { field: string; message: string }[] | undefined, planIds: number[] = []): TrafficErrors {
  const out: TrafficErrors = {};
  for (const f of fields ?? []) out[trafficFieldKey(f.field, planIds)] ??= f.message;
  return out;
}

// ---------- apresentação ----------

export const SCOPE_LABEL: Record<Scope, string> = { x: "Cruzamento", a1: "Aproximação 1", a2: "Aproximação 2" };

export interface MetricInfo { label: string; unit: string; kind: "time" | "count" | "rate" | "fraction"; hint: string }
export const METRICS: Record<string, MetricInfo> = {
  delay_censored: { label: "Atraso médio (com pendentes)", unit: "s", kind: "time", hint: "Inclui quem ainda espera no fim, contado só até T: é um limite inferior do atraso verdadeiro." },
  delay: { label: "Atraso médio (concluídos)", unit: "s", kind: "time", hint: "Só quem já cruzou. Com fila crescendo, parece melhor do que a realidade." },
  queue_mean: { label: "Fila média", unit: "veíc.", kind: "count", hint: "Veículos esperando, média no tempo." },
  queue_max: { label: "Fila máxima", unit: "veíc.", kind: "count", hint: "Maior fila na janela de medição." },
  queue_end: { label: "Fila ao fim", unit: "veíc.", kind: "count", hint: "Veículos ainda na fila quando a simulação acaba." },
  throughput: { label: "Vazão atendida", unit: "veíc./min", kind: "rate", hint: "Veículos que cruzam a linha de retenção por minuto." },
  stopped_fraction: { label: "Veículos que pararam", unit: "%", kind: "fraction", hint: "Fração que teve de esperar (atraso > 0)." },
  overflow_cycles: { label: "Ciclos que terminam com fila", unit: "%", kind: "fraction", hint: "Falha de ciclo: sobra fila ao fim do verde." },
  arrivals: { label: "Chegadas", unit: "veíc.", kind: "count", hint: "Veículos que chegaram na janela de medição." },
  departures: { label: "Saídas", unit: "veíc.", kind: "count", hint: "Veículos que cruzaram na janela de medição." },
  pending: { label: "Pendentes", unit: "veíc.", kind: "count", hint: "Chegaram e ainda esperavam no fim." },
};
export const HEADLINE_METRICS = ["delay_censored", "delay", "queue_mean", "queue_max", "queue_end", "throughput", "stopped_fraction", "overflow_cycles"];
export const COMPARE_METRICS = ["delay_censored", "delay", "queue_mean", "queue_max", "queue_end", "throughput", "overflow_cycles"];

const fmt = (digits: number) => new Intl.NumberFormat("pt-BR", { minimumFractionDigits: digits, maximumFractionDigits: digits });
const sig = (v: number) => {
  const a = Math.abs(v);
  const d = a >= 100 ? 0 : a >= 10 ? 1 : 2;
  return fmt(d).format(v);
};

/** Valor na unidade da tela (vazão em veíc./min; frações em %). */
export function scaleMetric(name: string, v: number): number {
  const kind = METRICS[name]?.kind;
  return kind === "rate" ? v * 60 : kind === "fraction" ? v * 100 : v;
}
export function formatMetricValue(name: string, v: number | null | undefined): string {
  return v === null || v === undefined ? "—" : sig(scaleMetric(name, v));
}
export function formatSummary(name: string, s: Summary | null | undefined): string {
  if (!s) return "—";
  const base = formatMetricValue(name, s.mean);
  return s.ci_low === null || s.ci_low === undefined || s.ci_high === null || s.ci_high === undefined
    ? base : `${base} [${formatMetricValue(name, s.ci_low)}; ${formatMetricValue(name, s.ci_high)}]`;
}
export function formatDelta(name: string, s: Summary | null | undefined): string {
  if (!s) return "—";
  const v = scaleMetric(name, s.mean);
  const sign = v > 0 ? "+" : v < 0 ? "−" : "";
  return `${sign}${sig(Math.abs(v))}`;
}
export const formatSeconds = (v: number | null | undefined) => (v === null || v === undefined ? "—" : `${sig(v)} s`);
export const formatSaturation = (x: number) => fmt(2).format(x);
export const perMinute = (perSecond: number) => perSecond * 60;
export const formatRatePerMin = (perSecond: number) => `${sig(perMinute(perSecond))} veíc./min`;

export const NOT_INFORMED_LABEL: Record<string, string> = {
  first_vehicle_time: "tempo do 1º veículo (ℓ)", amber_usable: "amarelo utilizável", initial_queue: "fila inicial",
};

export function alertTone(a: TrafficAlert): "bad" | "warn" | "info" {
  if (a.code === "oversaturated") return "bad";
  return a.level === "info" ? "info" : "warn";
}

export const VERDICT_TEXT: Record<"higher" | "lower" | "inconclusive", string> = {
  higher: "aumenta", lower: "reduz", inconclusive: "inconclusivo",
};
/** O veredito vira "melhor", "pior" ou neutro conforme o sentido bom da métrica. */
export function verdictTone(verdict: "higher" | "lower" | "inconclusive" | null, better: "lower" | "higher" | null): "good" | "bad" | "neutral" {
  if (!verdict || verdict === "inconclusive" || !better) return "neutral";
  return verdict === better ? "good" : "bad";
}

export function phaseText(p: Phase): string {
  return `${sig(p.green)} + ${sig(p.amber)} + ${sig(p.all_red)} s`;
}

// ---------- aplicar as estimativas do vídeo ao formulário ----------

const text = (v: number | null | undefined, digits = 3): string =>
  v === null || v === undefined ? "" : String(Number(v.toFixed(digits)));

/** Preenche o formulário com o que o vídeo estimou; o que não foi estimado fica vazio (não informado). */
export function applyEstimate(current: TrafficText, estimate: VideoEstimate): TrafficText {
  const s: SuggestedBody = estimate.suggested;
  const phase = (i: 0 | 1) => ({ g: text(s.phases[i].green, 2), y: text(s.phases[i].amber, 2), r: text(s.phases[i].all_red, 2) });
  const p1 = phase(0), p2 = phase(1);
  const approaches = s.approaches.map((a, i): ApproachText => {
    const h = a.headway;
    const distribution = (HEADWAY_ORDER as string[]).includes(h?.distribution ?? "") ? (h!.distribution as HeadwayDistribution) : current.approaches[i].distribution;
    return {
      name: estimate.approach_ids[i] ?? a.name,
      rate: "",
      profile: a.profile.map((b) => ({ duration: text(b.duration, 1), rate: text(b.lambda * 60, 3) })),
      distribution,
      headwayMean: text(h?.mean), headwayCv: text(h?.cv), headwayK: text(h?.k, 0),
      firstVehicle: text(a.first_vehicle_time, 2), amberUsable: text(a.amber_usable, 2),
      initialQueue: a.initial_queue === null ? "" : String(a.initial_queue),
    };
  }) as [ApproachText, ApproachText];
  return {
    ...current,
    green1: p1.g, amber1: p1.y, allRed1: p1.r, green2: p2.g, amber2: p2.y, allRed2: p2.r,
    offset: text(s.offset, 2), approaches, simulationTime: String(Math.floor(s.simulation_time)), warmupTime: "0",
  };
}

export const approachName = (result: { approaches: { key: ApproachKey; name: string }[] }, key: ApproachKey) =>
  result.approaches.find((a) => a.key === key)?.name ?? (key === "a1" ? "Aproximação 1" : "Aproximação 2");
