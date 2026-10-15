import type { CompareBody, Level } from "../api/realdata";
import type { LevelSuggestions, SimulatedCompareBody, SimulationBody } from "../api/realdataExtra";
import { MAX_UPLOAD_BYTES } from "./realdata";

const toNumber = (text: string): number => Number(text.trim().replace(",", "."));
const INTEGER = "Informe um número inteiro.";
const NUMBER = "Informe um número.";

// ---------- simulação opcional ("Simular também") ----------

export interface SimulationText { enabled: boolean; simulationTime: string; replications: string; warmupTime: string; seed: string }
export type SimulationErrors = Partial<Record<"simulationTime" | "replications" | "warmupTime" | "seed", string>>;

/** Desligada por padrão: a comparação só analítica continua sendo o comportamento de antes. */
export const INITIAL_SIM: SimulationText = {
  enabled: false, simulationTime: "1000", replications: "10", warmupTime: "50", seed: "2026",
};

/** Só confere o formato; os limites (réplicas, custo) são regras da API. */
export function buildSimulation(sim: SimulationText): { ok: true; body: SimulationBody } | { ok: false; errors: SimulationErrors } {
  const errors: SimulationErrors = {};
  const time = toNumber(sim.simulationTime);
  const reps = toNumber(sim.replications);
  const warmup = toNumber(sim.warmupTime);
  const seedText = sim.seed.trim();
  if (sim.simulationTime.trim() === "" || !Number.isFinite(time)) errors.simulationTime = NUMBER;
  if (sim.replications.trim() === "" || !Number.isInteger(reps)) errors.replications = INTEGER;
  if (sim.warmupTime.trim() === "" || !Number.isFinite(warmup)) errors.warmupTime = NUMBER;
  if (seedText !== "" && !Number.isInteger(toNumber(seedText))) errors.seed = INTEGER;
  if (Object.keys(errors).length > 0) return { ok: false, errors };
  return {
    ok: true,
    body: {
      simulation_time: time, replications: reps, warmup_time: warmup, confidence_level: 0.95,
      ...(seedText === "" ? {} : { seed: toNumber(seedText) }),
    },
  };
}

const SIM_API_TO_FIELD: Record<string, keyof SimulationErrors> = {
  simulation_time: "simulationTime", replications: "replications", warmup_time: "warmupTime", seed: "seed",
};

export function simulationErrorsFromApi(fields: { field: string; message: string }[] | undefined): SimulationErrors {
  const out: SimulationErrors = {};
  for (const issue of fields ?? []) {
    const key = SIM_API_TO_FIELD[issue.field];
    if (key) out[key] = issue.message;
  }
  return out;
}

// ---------- níveis de carga (CSV agregado) ----------

export type LevelsModelKey = "mm1" | "mmc" | "mm1k" | "mmck" | "mm1n" | "mmcn";

export const LEVELS_MODELS: { key: LevelsModelKey; label: string }[] = [
  { key: "mm1n", label: "M/M/1//N — fechado, 1 servidor" },
  { key: "mmcn", label: "M/M/c//N — fechado, c servidores" },
  { key: "mm1", label: "M/M/1 — aberto" },
  { key: "mmc", label: "M/M/c — aberto, c servidores" },
  { key: "mm1k", label: "M/M/1/K — aberto, capacidade K" },
  { key: "mmck", label: "M/M/c/K — aberto, c servidores e K" },
];

export const needsServers = (m: LevelsModelKey) => m === "mmc" || m === "mmck" || m === "mmcn";
export const needsCapacity = (m: LevelsModelKey) => m === "mm1k" || m === "mmck";
export const needsThinkTime = (m: LevelsModelKey) => m === "mm1n" || m === "mmcn";

export interface LevelsText { model: LevelsModelKey; mu: string; servers: string; capacity: string; thinkTime: string }
export type LevelsErrors = Partial<Record<"file" | keyof LevelsText, string>>;

export const INITIAL_LEVELS: LevelsText = { model: "mm1n", mu: "", servers: "1", capacity: "", thinkTime: "" };

/** Texto de um número para o campo do formulário (4 algarismos significativos). */
export const toFieldText = (value: number): string => String(Number(value.toPrecision(4)));

/** Preenche μ e Z com a calibração sugerida no menor nível, sem sobrescrever o que o usuário já digitou. */
export function applySuggestions(t: LevelsText, s: LevelSuggestions): LevelsText {
  return {
    ...t,
    mu: t.mu.trim() === "" && s.mu != null ? toFieldText(s.mu) : t.mu,
    thinkTime: t.thinkTime.trim() === "" && s.think_time != null ? toFieldText(s.think_time) : t.thinkTime,
  };
}

export function validateLevelsFile(file: File | null): string | null {
  if (!file) return "Escolha o arquivo CSV com os níveis de carga.";
  if (!file.name.toLowerCase().endsWith(".csv")) return "O arquivo precisa ter a extensão .csv.";
  if (file.size === 0) return "O arquivo está vazio.";
  if (file.size > MAX_UPLOAD_BYTES) return `O arquivo passa do limite de ${MAX_UPLOAD_BYTES / (1024 * 1024)} MB.`;
  return null;
}

export function buildLevelsForm(file: File | null): { ok: true; form: FormData } | { ok: false; error: string } {
  const error = validateLevelsFile(file);
  if (error || !file) return { ok: false, error: error ?? "Escolha o arquivo." };
  const form = new FormData();
  form.append("file", file);
  return { ok: true, form };
}

export type LevelsCompare =
  | { ok: true; body: CompareBody | SimulatedCompareBody; simulated: boolean }
  | { ok: false; errors: LevelsErrors & SimulationErrors };

/** Monta a comparação dos níveis importados com o modelo escolhido (com ou sem simulação). */
export function buildLevelsCompare(levels: Level[], t: LevelsText, sim: SimulationText): LevelsCompare {
  const errors: LevelsErrors & SimulationErrors = {};
  const mu = toNumber(t.mu);
  if (t.mu.trim() === "" || !Number.isFinite(mu)) errors.mu = NUMBER;
  let servers = 1;
  if (needsServers(t.model)) {
    servers = toNumber(t.servers);
    if (t.servers.trim() === "" || !Number.isInteger(servers)) errors.servers = INTEGER;
  }
  let capacity: number | undefined;
  if (needsCapacity(t.model)) {
    capacity = toNumber(t.capacity);
    if (t.capacity.trim() === "" || !Number.isInteger(capacity)) errors.capacity = INTEGER;
  }
  let think: number | undefined;
  if (needsThinkTime(t.model)) {
    think = toNumber(t.thinkTime);
    if (t.thinkTime.trim() === "" || !Number.isFinite(think)) errors.thinkTime = NUMBER;
  }
  const built = sim.enabled ? buildSimulation(sim) : null;
  if (built && !built.ok) Object.assign(errors, built.errors);
  if (Object.keys(errors).length > 0) return { ok: false, errors };

  const body: CompareBody = {
    model: t.model, mu, servers,
    ...(capacity === undefined ? {} : { capacity }),
    ...(think === undefined ? {} : { think_time: think }),
    levels,
  };
  return built?.ok ? { ok: true, body: { ...body, simulation: built.body }, simulated: true } : { ok: true, body, simulated: false };
}

const LEVELS_API_TO_FIELD: Record<string, keyof LevelsErrors> = {
  file: "file", model: "model", mu: "mu", servers: "servers", capacity: "capacity", think_time: "thinkTime",
};

export function levelsErrorsFromApi(fields: { field: string; message: string }[] | undefined): LevelsErrors & SimulationErrors {
  const out: LevelsErrors & SimulationErrors = { ...simulationErrorsFromApi(fields) };
  for (const issue of fields ?? []) {
    const key = LEVELS_API_TO_FIELD[issue.field];
    if (key) out[key] = issue.message;
  }
  return out;
}
