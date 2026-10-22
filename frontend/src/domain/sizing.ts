import { parseNumber } from "./number";
import { MODELS } from "./models";
import { readSystem, reader, type Body, type Built, type ExpErrors, type SystemText } from "./experiments";
import type { ExperimentModelKey } from "./types";

/** Tabela, menor c pela meta (nível de serviço ou bloqueio) e custo mínimo. */
export type SizingAction = "table" | "sla" | "cost";

/** O Laboratório usa req/s; os custos podem ser digitados por segundo, minuto ou hora. */
export type CostUnit = "s" | "min" | "h";
export const COST_UNITS: { key: CostUnit; label: string; seconds: number }[] = [
  { key: "s", label: "por segundo", seconds: 1 },
  { key: "min", label: "por minuto", seconds: 60 },
  { key: "h", label: "por hora", seconds: 3600 },
];
export const secondsIn = (unit: CostUnit): number => COST_UNITS.find((u) => u.key === unit)!.seconds;

/** Campos do formulário de dimensionamento, como digitados (metas em %, custos na unidade escolhida). */
export interface SizingText {
  cMin: string;
  cMax: string;
  t: string;          // tempo-limite, em segundos
  target: string;     // nível de serviço alvo, em %
  blocking: string;   // bloqueio alvo, em % (Erlang-B)
  serverCost: string;
  waitCost: string;
  lossCost: string;
  costUnit: CostUnit;
}

export const INITIAL_SIZING: SizingText = {
  cMin: "", cMax: "", t: "20", target: "80", blocking: "1",
  serverCost: "35", waitCost: "80", lossCost: "", costUnit: "h",
};

/** No Erlang-B não há espera: a meta é o bloqueio e o custo de espera não existe. */
export const hasWaiting = (model: ExperimentModelKey): boolean => model !== "erlangb";
/** Modelos com perda: o custo ganha o termo λ·B·h_perda. */
export const hasLoss = (model: ExperimentModelKey): boolean =>
  model === "erlangb" || model === "mm1k" || model === "mmck";

/** Aviso de que o modelo é dimensionado pela família com c (M/M/1 é o caso c = 1 do M/M/c, etc.). */
export function familyNote(model: ExperimentModelKey): string | null {
  const notes: Partial<Record<ExperimentModelKey, string>> = {
    mm1: "O M/M/1 não tem c para dimensionar: a aba usa o M/M/c (o M/M/1 é o caso c = 1), com os mesmos λ e μ.",
    mm1k: "O M/M/1/K não tem c para dimensionar: a aba usa o M/M/c/K (o M/M/1/K é o caso c = 1), com os mesmos λ, μ e K. Aqui c fica limitado a K.",
    mmck: "No M/M/c/K o c fica limitado a K (a capacidade total).",
    mg1: "O M/G/1 não tem c para dimensionar: a aba usa o M/G/c (o M/G/1 é o caso c = 1), com o mesmo serviço.",
  };
  return notes[model] ?? null;
}

function optionalNumber(text: string): number | null {
  if (text.trim() === "") return null;
  return parseNumber(text);
}

/** Corpo de POST /api/sizing/{table,sla,cost}. Só confere o formato; as regras ficam na API. */
export function buildSizingBody(
  action: SizingAction, model: ExperimentModelKey, system: SystemText, text: SizingText,
): Built<Body> {
  const errors: ExpErrors = {};
  const read = reader(errors);
  const body: Body = { model, ...readSystem(model, system, null, errors) };

  const number = (key: string, value: string, label: string, scale = 1): number | null => {
    const n = optionalNumber(value);
    if (n === null) return null;
    if (!Number.isFinite(n)) { errors[key] = `${label}: informe um número.`; return null; }
    return n * scale;
  };

  // Janela de c (a tabela e o custo; no SLA o c é o menor que atinge a meta)
  if (action !== "sla") {
    for (const [key, field, value] of [["cMin", "c_min", text.cMin], ["cMax", "c_max", text.cMax]] as const) {
      if (value.trim() === "") continue;
      body[field] = read(key, value, true);
    }
  }

  // Metas
  const wait = hasWaiting(model);
  const t = wait ? number("t", text.t, "Tempo-limite") : null;
  const target = wait ? number("target", text.target, "Meta", 1 / 100) : null;
  const blocking = !wait ? number("blocking", text.blocking, "Bloqueio alvo", 1 / 100) : null;
  if (action === "sla") {
    if (wait && (t === null || target === null)) {
      if (t === null) errors.t = "Informe o tempo-limite.";
      if (target === null) errors.target = "Informe a meta de nível de serviço.";
    }
    if (!wait && blocking === null) errors.blocking = "Informe o bloqueio alvo.";
  }
  if (wait && (t === null) !== (target === null) && action !== "sla") {
    errors[t === null ? "t" : "target"] = "Informe o tempo-limite e a meta juntos (ou deixe os dois vazios).";
  }
  if (t !== null && target !== null) { body.t = t; body.target = target; }
  if (blocking !== null) body.target_blocking = blocking;

  // Custos: convertidos para a unidade de tempo de λ e μ (por segundo) antes de enviar
  if (action !== "sla") {
    const perSecond = 1 / secondsIn(text.costUnit);
    const server = number("serverCost", text.serverCost, "Custo do servidor", perSecond);
    const waitCost = wait ? number("waitCost", text.waitCost, "Custo da espera", perSecond) : 0;
    const loss = hasLoss(model) ? number("lossCost", text.lossCost, "Custo da perda", perSecond) : null;
    const any = server !== null || (wait && waitCost !== null) || loss !== null;
    if (action === "cost" || any) {
      if (server === null) errors.serverCost ??= "Informe o custo do servidor.";
      if (wait && waitCost === null) errors.waitCost ??= "Informe o custo da espera.";
      if (model === "erlangb" && (loss === null || loss <= 0)) errors.lossCost ??= "No Erlang-B o custo exige um custo de perda maior que zero.";
      if (server !== null) body.server_cost = server;
      if (waitCost !== null) body.wait_cost = waitCost;
      if (loss !== null) body.loss_cost = loss;
    }
  }
  return Object.keys(errors).length > 0 ? { ok: false, errors } : { ok: true, body };
}

export const infoLabel = (model: ExperimentModelKey): string => MODELS[model].label;
