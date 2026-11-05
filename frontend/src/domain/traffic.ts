/**
 * Cruzamento semaforizado (Fases 13.1 e 13.2): o formulário, o corpo dos pedidos e a leitura dos erros da API.
 *
 * Na tela, as taxas de chegada são em veículos por minuto (como se conta no vídeo) e os tempos em segundos;
 * a API trabalha em veículos por segundo. Os parâmetros que vêm da medição no vídeo (ℓ, amarelo utilizável,
 * fila inicial, offset) começam vazios: vazio = "não informado", e a API avisa que assumiu 0.
 *
 * O cruzamento tem de 2 a 4 fases e uma aproximação por fase (a fase i atende a aproximação i). Cada aproximação
 * pode ter classes de veículos (carro, moto, ônibus...), cujo fator de equivalência em carros não tem valor padrão.
 */
import type {
  ApproachKey, Phase, Scope, Summary, SuggestedBody, TrafficAlert, VideoEstimate,
} from "../api/traffic";
import { parseNumber } from "./number";

export const MAX_PLANS = 10;
export const MAX_SWEEP_POINTS = 40;
export const MIN_PHASES = 2;
export const MAX_PHASES = 4;
export const MAX_CLASSES = 8;

export type HeadwayDistribution = "deterministic" | "exponential" | "lognormal" | "weibull" | "erlang";
export const HEADWAY_LABEL: Record<HeadwayDistribution, string> = {
  deterministic: "Determinístico", exponential: "Exponencial", lognormal: "Lognormal", weibull: "Weibull", erlang: "Erlang-k",
};
export const HEADWAY_ORDER: HeadwayDistribution[] = ["deterministic", "lognormal", "weibull", "erlang", "exponential"];

/** Bloco do perfil de chegadas. Com `count`, reproduz a contagem observada (e `classCounts` por classe). */
export interface ProfileBlockText {
  duration: string; rate: string;               // duração em s e taxa em veículos/min
  count?: string; classCounts?: Record<string, string>;
}
export interface ClassText { name: string; share: string; factor: string }
export interface PhaseText { green: string; amber: string; allRed: string }

export interface ApproachText {
  name: string;
  rate: string;                       // veículos/min (constante); ignorada se houver `profile`
  profile: ProfileBlockText[] | null; // perfil por blocos vindo do vídeo
  distribution: HeadwayDistribution;
  headwayMean: string;                // s (por carro equivalente, se houver classes)
  headwayCv: string;
  headwayK: string;
  firstVehicle: string;               // ℓ (s)
  firstVehicleCv: string;             // CV de ℓ entre ciclos (vazio ou 0 = constante)
  amberUsable: string;                // s
  initialQueue: string;               // veículos
  classes: ClassText[];               // vazio = só carros
}

export interface TrafficText {
  phases: PhaseText[];
  offset: string;
  approaches: ApproachText[];
  simulationTime: string; replications: string; warmupTime: string; seed: string; seriesStep: string;
}

export interface PlanText { id: number; name: string; phases: PhaseText[] }
/** Varredura: as duas fases (1 a 4) cujo verde é redistribuído e o verde mínimo de cada uma. */
export interface SweepText { pair1: string; pair2: string; minGreen1: string; minGreen2: string; step: string }

export const blankPhase = (): PhaseText => ({ green: "", amber: "", allRed: "" });
export const blankClass = (): ClassText => ({ name: "", share: "", factor: "" });

export const blankApproach = (name: string): ApproachText => ({
  name, rate: "", profile: null, distribution: "lognormal", headwayMean: "", headwayCv: "", headwayK: "",
  firstVehicle: "", firstVehicleCv: "", amberUsable: "", initialQueue: "", classes: [],
});

export function blankTraffic(): TrafficText {
  return {
    phases: [blankPhase(), blankPhase()], offset: "",
    approaches: [blankApproach("Aproximação 1"), blankApproach("Aproximação 2")],
    simulationTime: "3600", replications: "20", warmupTime: "0", seed: "2026", seriesStep: "",
  };
}

/** Valores HIPOTÉTICOS para conhecer a tela. Não são medições de nenhum cruzamento real. */
export function exampleTraffic(): TrafficText {
  const phase = (g: string): PhaseText => ({ green: g, amber: "3", allRed: "2" });
  return {
    ...blankTraffic(),
    phases: [phase("30"), phase("25")], offset: "0",
    approaches: [
      { ...blankApproach("Aproximação 1"), rate: "12", distribution: "lognormal", headwayMean: "2", headwayCv: "0.3", firstVehicle: "2.4", amberUsable: "1", initialQueue: "0" },
      { ...blankApproach("Aproximação 2"), rate: "9.6", distribution: "lognormal", headwayMean: "2", headwayCv: "0.3", firstVehicle: "2.4", amberUsable: "1", initialQueue: "0" },
    ],
  };
}

export const blankPlan = (id: number, name = "", phases = 2): PlanText => ({
  id, name, phases: Array.from({ length: phases }, blankPhase),
});

export const blankSweep = (): SweepText => ({ pair1: "1", pair2: "2", minGreen1: "", minGreen2: "", step: "5" });

/** Muda o número de fases: a fase e a aproximação novas entram vazias; ao remover, saem as últimas. */
export function resizePhases(form: TrafficText, count: number): TrafficText {
  const n = Math.min(MAX_PHASES, Math.max(MIN_PHASES, count));
  const phases = form.phases.slice(0, n);
  const approaches = form.approaches.slice(0, n);
  while (phases.length < n) phases.push(blankPhase());
  while (approaches.length < n) approaches.push(blankApproach(`Aproximação ${approaches.length + 1}`));
  return { ...form, phases, approaches };
}

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

function readPhases(r: Reader, phases: PhaseText[]) {
  return phases.map((p, i) => ({
    green: r.num(`green${i + 1}`, p.green, `o verde da fase ${i + 1}`, { required: true, positive: true }),
    amber: r.num(`amber${i + 1}`, p.amber, `o amarelo da fase ${i + 1}`) ?? 0,
    all_red: r.num(`allRed${i + 1}`, p.allRed, `o todo-vermelho da fase ${i + 1}`) ?? 0,
  }));
}

function readClasses(r: Reader, a: ApproachText, p: string, n: number) {
  if (a.classes.length === 0) return undefined;
  return a.classes.map((c, j) => {
    const name = trimmed(c.name);
    if (!name) r.errors[`${p}class.${j}.name`] = `Dê um nome à classe ${j + 1} da aproximação ${n}.`;
    return {
      name,
      share: r.num(`${p}class.${j}.share`, c.share, `a parcela da classe ${j + 1} da aproximação ${n} (0 a 1)`, { required: true }),
      factor: r.num(`${p}class.${j}.factor`, c.factor, `o fator de equivalência em carros da classe ${j + 1} da aproximação ${n}`, { required: true, positive: true }),
    };
  });
}

function readApproach(r: Reader, a: ApproachText, i: number) {
  const p = `a${i + 1}.`;
  const n = i + 1;
  const approach: Body = { name: trimmed(a.name) || `Aproximação ${n}` };
  if (a.profile) {
    approach.profile = a.profile.map((b, j) => {
      const block: Body = { duration: r.num(`${p}profile.${j}`, b.duration, `a duração do bloco ${j + 1}`, { required: true, positive: true }) };
      if (b.count !== undefined) {
        block.count = r.num(`${p}profile.${j}`, b.count, `a contagem do bloco ${j + 1}`, { required: true, integer: true });
        if (b.classCounts) {
          block.class_counts = Object.fromEntries(Object.entries(b.classCounts).map(([k, v]) => [k, parseNumber(v)]));
        }
      } else {
        block.lambda = (r.num(`${p}profile.${j}`, b.rate, `a taxa do bloco ${j + 1}`, { required: true }) ?? 0) / 60;
      }
      return block;
    });
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
  const cv = r.num(`${p}firstVehicleCv`, a.firstVehicleCv, `o CV do tempo do 1º veículo da aproximação ${n}`);
  if (cv !== null && cv !== undefined) approach.first_vehicle_cv = cv;
  approach.amber_usable = r.num(`${p}amberUsable`, a.amberUsable, `o amarelo utilizável da aproximação ${n}`);
  approach.initial_queue = r.num(`${p}initialQueue`, a.initialQueue, `a fila inicial da aproximação ${n}`, { integer: true });
  const classes = readClasses(r, a, p, n);
  if (classes) approach.classes = classes;
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
    phases: readPhases(r, f.phases),
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
    const phases = f.phases.map((_, i) => {
      const n = i + 1;
      const ph = p.phases[i] ?? blankPhase();
      const g = patch(`green${n}`, ph.green, `o verde da fase ${n}`);
      const y = patch(`amber${n}`, ph.amber, `o amarelo da fase ${n}`);
      const a = patch(`allRed${n}`, ph.allRed, `o todo-vermelho da fase ${n}`);
      return g === undefined && y === undefined && a === undefined ? null : { green: g, amber: y, all_red: a };
    });
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
  const n = f.phases.length;
  const a = r.num("pair1", s.pair1, "a primeira fase da varredura", { required: true, integer: true, positive: true });
  const b = r.num("pair2", s.pair2, "a segunda fase da varredura", { required: true, integer: true, positive: true });
  if (typeof a === "number" && (a > n)) r.errors.pair1 = `A fase deve estar entre 1 e ${n}.`;
  if (typeof b === "number" && (b > n)) r.errors.pair2 = `A fase deve estar entre 1 e ${n}.`;
  if (typeof a === "number" && typeof b === "number" && a === b) r.errors.pair2 = "Escolha duas fases diferentes.";
  const g1 = r.num("minGreen1", s.minGreen1, `o verde mínimo da fase ${s.pair1 || 1}`, { required: true, positive: true });
  const g2 = r.num("minGreen2", s.minGreen2, `o verde mínimo da fase ${s.pair2 || 2}`, { required: true, positive: true });
  const step = r.num("step", s.step, "o passo da varredura", { required: true, positive: true });
  const errors = { ...(base.ok ? {} : base.errors), ...r.errors };
  if (Object.keys(errors).length || !base.ok) return { ok: false, errors };
  const body: Body = { ...base.body, min_green: [g1, g2], step };
  if (!(a === 1 && b === 2)) body.pair = [a, b];
  return { ok: true, body };
}

// ---------- erros da API → campos do formulário ----------

const APPROACH_FIELD: Record<string, string> = {
  lambda: "rate", profile: "rate", first_vehicle_time: "firstVehicle", first_vehicle_cv: "firstVehicleCv", amber_usable: "amberUsable",
  initial_queue: "initialQueue", "headway.mean": "headwayMean", "headway.cv": "headwayCv", "headway.k": "headwayK",
  headway: "headwayMean", "headway.distribution": "headwayMean",
};
const PHASE_FIELD: Record<string, "green" | "amber" | "allRed"> = { green: "green", amber: "amber", all_red: "allRed" };
const RUN_FIELD: Record<string, string> = {
  simulation_time: "simulationTime", replications: "replications", warmup_time: "warmupTime", seed: "seed",
  series_step: "seriesStep", offset: "offset", step: "step", min_green: "minGreen1", scenarios: "plans", phases: "green1",
  pair: "pair1",
};

/** "approaches.1.headway.cv" → "a2.headwayCv"; "scenarios.0.phases.1.green" → "plan:0.green2". `planIds` traduz a posição em id. */
export function trafficFieldKey(field: string, planIds: number[] = []): string {
  const parts = field.split(".");
  if (parts[0] === "approaches" && parts.length >= 3) {
    const rest = parts.slice(2).join(".");
    const cls = /^classes\.(\d+)\.(name|share|factor)$/.exec(rest);
    if (cls) return `a${Number(parts[1]) + 1}.class.${cls[1]}.${cls[2]}`;
    if (rest === "classes" || rest.startsWith("classes.")) return `a${Number(parts[1]) + 1}.class.0.share`;
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

export const SCOPE_LABEL: Record<Scope, string> = { x: "Cruzamento", a1: "Aproximação 1", a2: "Aproximação 2", a3: "Aproximação 3", a4: "Aproximação 4" };

export interface MetricInfo { label: string; unit: string; kind: "time" | "count" | "rate" | "fraction"; hint: string }
export const METRICS: Record<string, MetricInfo> = {
  delay_censored: { label: "Atraso médio (com pendentes)", unit: "s", kind: "time", hint: "Inclui quem ainda espera no fim, contado só até T: é um limite inferior do atraso verdadeiro." },
  delay: { label: "Atraso médio (concluídos)", unit: "s", kind: "time", hint: "Só quem já cruzou. Com fila crescendo, parece melhor do que a realidade." },
  queue_mean: { label: "Fila média", unit: "veíc.", kind: "count", hint: "Veículos esperando, média no tempo." },
  queue_max: { label: "Fila máxima", unit: "veíc.", kind: "count", hint: "Maior fila na janela de medição." },
  queue_end: { label: "Fila ao fim", unit: "veíc.", kind: "count", hint: "Veículos ainda na fila quando a simulação acaba." },
  throughput: { label: "Vazão atendida", unit: "veíc./min", kind: "rate", hint: "Veículos que cruzam a linha de retenção por minuto." },
  throughput_ceq: { label: "Vazão em carros equivalentes", unit: "ceq./min", kind: "rate", hint: "Cada veículo que cruza vale o fator da sua classe (igual à vazão sem classes)." },
  stopped_fraction: { label: "Veículos que esperaram", unit: "%", kind: "fraction", hint: "Fração com atraso > 0 (inclui quem esperou só o intervalo do veículo da frente). Não é a contagem visual de parados." },
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

/** Texto de uma decisão de teste de hipótese. */
export const DECISION_TEXT: Record<string, string> = {
  rejected: "rejeitado", not_rejected: "não rejeitado", not_evaluated: "não avaliado",
  equivalent: "equivalente", not_shown: "equivalência não demonstrada",
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

/**
 * Preenche o formulário com o que o vídeo estimou; o que não foi estimado fica vazio (não informado).
 * Com `replay`, o perfil de chegadas traz as contagens observadas (e por classe) em vez de taxas: o plano
 * enfrenta exatamente as chegadas filmadas. Os fatores de equivalência das classes vêm de quem os informou.
 */
export function applyEstimate(current: TrafficText, estimate: VideoEstimate, replay = false): TrafficText {
  const s: SuggestedBody = replay && estimate.suggested.replay ? { ...estimate.suggested.replay } : estimate.suggested;
  const phases = s.phases.map((p): PhaseText => ({ green: text(p.green, 2), amber: text(p.amber, 2), allRed: text(p.all_red, 2) }));
  const approaches = s.approaches.map((a, i): ApproachText => {
    const h = a.headway;
    const distribution = (HEADWAY_ORDER as string[]).includes(h?.distribution ?? "") ? (h!.distribution as HeadwayDistribution) : (current.approaches[i]?.distribution ?? "lognormal");
    return {
      name: estimate.approach_ids[i] ?? a.name,
      rate: "",
      profile: a.profile.map((b) => {
        const block: ProfileBlockText = { duration: text(b.duration, 1), rate: text((b.lambda ?? (b.count ?? 0) / b.duration) * 60, 3) };
        if (replay && b.count !== undefined) {
          block.count = String(b.count);
          if (b.class_counts) block.classCounts = Object.fromEntries(Object.entries(b.class_counts).map(([k, v]) => [k, String(v)]));
        }
        return block;
      }),
      distribution,
      headwayMean: text(h?.mean), headwayCv: text(h?.cv), headwayK: text(h?.k, 0),
      firstVehicle: text(a.first_vehicle_time, 2), firstVehicleCv: text(a.first_vehicle_cv, 3), amberUsable: text(a.amber_usable, 2),
      initialQueue: a.initial_queue === null ? "" : String(a.initial_queue),
      classes: (a.classes ?? []).map((c) => ({ name: c.name, share: text(c.share, 4), factor: text(c.factor, 3) })),
    };
  });
  return {
    ...current,
    phases, offset: text(s.offset, 2), approaches, simulationTime: String(Math.floor(s.simulation_time)), warmupTime: "0",
  };
}

export const approachName = (result: { approaches: { key: ApproachKey; name: string }[] }, key: ApproachKey) =>
  result.approaches.find((a) => a.key === key)?.name ?? `Aproximação ${key.slice(1)}`;

/** "carro=1; moto=0,35; ônibus=2,2" → {"carro": 1, "moto": 0.35, "ônibus": 2.2}. Devolve a mensagem de erro se não der. */
export function parseClassFactors(textValue: string): Record<string, number> | string | null {
  const t = textValue.trim();
  if (t === "") return null;
  const out: Record<string, number> = {};
  for (const part of t.split(/[;\n]+/).map((x) => x.trim()).filter(Boolean)) {
    const [name, value] = part.split("=").map((x) => x.trim());
    const v = value === undefined ? NaN : parseNumber(value);
    if (!name || !Number.isFinite(v) || v <= 0) return `Fator inválido em “${part}”: use nome=fator, com fator maior que zero (ex.: moto=0,35).`;
    out[name] = v;
  }
  return out;
}
