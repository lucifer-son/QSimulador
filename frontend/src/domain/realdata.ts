import type {
  AnalysisResponse, CompareBody, Confidence, CriterionId, DiagnosticStatus,
} from "../api/realdata";

export type SystemType = "auto" | "open" | "closed";

/** Contexto opcional do teste, como o usuário digita (texto). */
export interface RealDataText {
  systemType: SystemType;
  servers: string;
  serviceTime: string;
  thinkTime: string;
  capacity: string;
  trimStart: string;
  trimEnd: string;
}

export const INITIAL_TEXT: RealDataText = {
  systemType: "auto", servers: "", serviceTime: "", thinkTime: "", capacity: "", trimStart: "10", trimEnd: "10",
};

/** RNF-25 (proposto): o mesmo limite que a API aplica. */
export const MAX_UPLOAD_BYTES = 10 * 1024 * 1024;

export type RealDataErrors = Partial<Record<"file" | keyof RealDataText, string>>;

const toNumber = (text: string): number => Number(text.trim().replace(",", "."));

export type BuiltForm = { ok: true; form: FormData } | { ok: false; errors: RealDataErrors };

/** Valida o que dá para validar no navegador e monta o multipart. Só envia o que foi preenchido. */
export function buildAnalyzeForm(file: File | null, t: RealDataText): BuiltForm {
  const errors: RealDataErrors = {};
  if (!file) errors.file = "Escolha o arquivo CSV exportado pelo JMeter.";
  else if (!file.name.toLowerCase().endsWith(".csv")) errors.file = "O arquivo precisa ter a extensão .csv.";
  else if (file.size === 0) errors.file = "O arquivo está vazio.";
  else if (file.size > MAX_UPLOAD_BYTES) errors.file = `O arquivo passa do limite de ${MAX_UPLOAD_BYTES / (1024 * 1024)} MB.`;

  const optional = (key: keyof RealDataText, ok: (n: number) => boolean, message: string) => {
    const text = t[key].trim();
    if (text !== "" && !(Number.isFinite(toNumber(text)) && ok(toNumber(text)))) errors[key] = message;
  };
  optional("servers", (n) => Number.isInteger(n) && n >= 1, "Informe um inteiro maior ou igual a 1.");
  optional("capacity", (n) => Number.isInteger(n) && n >= 1, "Informe um inteiro maior ou igual a 1.");
  optional("serviceTime", (n) => n > 0, "Informe um tempo maior que zero.");
  optional("thinkTime", (n) => n >= 0, "Informe um tempo maior ou igual a zero.");
  for (const key of ["trimStart", "trimEnd"] as const) {
    const n = toNumber(t[key]);
    if (t[key].trim() === "" || !Number.isFinite(n) || n < 0 || n >= 50) errors[key] = "Informe um valor de 0 a 50 (%).";
  }
  if (Object.keys(errors).length > 0 || !file) return { ok: false, errors };

  const form = new FormData();
  form.append("file", file);
  form.append("system_type", t.systemType);
  const add = (name: string, text: string) => {
    if (text.trim() !== "") form.append(name, String(toNumber(text)));
  };
  add("servers", t.servers);
  add("service_time_s", t.serviceTime);
  add("think_time_s", t.thinkTime);
  add("capacity", t.capacity);
  add("trim_start_pct", t.trimStart);
  add("trim_end_pct", t.trimEnd);
  return { ok: true, form };
}

const API_TO_FIELD: Record<string, keyof RealDataErrors> = {
  file: "file", system_type: "systemType", servers: "servers", service_time_s: "serviceTime",
  think_time_s: "thinkTime", capacity: "capacity", trim_start_pct: "trimStart", trim_end_pct: "trimEnd",
};

export function errorsFromApi(fields: { field: string; message: string }[] | undefined): RealDataErrors {
  const out: RealDataErrors = {};
  for (const issue of fields ?? []) {
    const key = API_TO_FIELD[issue.field];
    if (key) out[key] = issue.message;
  }
  return out;
}

export const CRITERIA_LABEL: Record<CriterionId, string> = {
  estrutura: "Estrutura (aberto ou fechado)",
  capacidade: "Capacidade (rejeições)",
  servidores: "Servidores",
  dados: "Dados (N e Z)",
  estabilidade: "Estabilidade",
  calibracao: "Calibração de μ",
  previsao: "Previsão do modelo",
};

export const CRITERIA_ORDER: CriterionId[] = ["estrutura", "capacidade", "servidores", "dados", "estabilidade", "calibracao", "previsao"];

export const CONFIDENCE_LABEL: Record<Confidence, string> = { alta: "alta", media: "média", baixa: "baixa" };

export const DIAGNOSTIC_LABEL: Record<DiagnosticStatus, string> = {
  ok: "Ok", atencao: "Atenção", critico: "Crítico", info: "Informação",
};

export type Tone = "success" | "warning" | "info";

export function bannerTone(result: AnalysisResponse): Tone {
  if (result.status === "no_good_fit") return "warning";
  return result.confidence === "alta" ? "success" : result.confidence === "media" ? "info" : "warning";
}

export interface ModelOption { key: string; notation: string; mu: number; disabled: string | null }

const NEEDS_CAPACITY = new Set(["mm1k", "mmck"]);
const NEEDS_POPULATION = new Set(["mm1n", "mmcn"]);

/** Modelos que o usuário pode recomparar com as medições (RF-24), sem refazer a análise. */
export function modelOptions(result: AnalysisResponse): ModelOption[] {
  const { estimates, levels } = result;
  return result.ranking
    .filter((r): r is typeof r & { mu: number } => r.mu !== null)
    .map((r) => {
      let disabled: string | null = null;
      if (NEEDS_CAPACITY.has(r.key) && !estimates.capacity) disabled = "sem rejeições, a capacidade K não é conhecida";
      else if (NEEDS_POPULATION.has(r.key) && (estimates.think_time == null || levels.some((l) => !l.users))) {
        disabled = "falta N (allThreads) ou Z";
      }
      return { key: r.key, notation: r.notation, mu: r.mu, disabled };
    });
}

export function compareBody(result: AnalysisResponse, option: ModelOption): CompareBody {
  const { estimates } = result;
  return {
    model: option.key, mu: option.mu, servers: estimates.servers,
    ...(estimates.capacity ? { capacity: estimates.capacity } : {}),
    ...(estimates.think_time != null ? { think_time: estimates.think_time } : {}),
    levels: result.levels,
  };
}
