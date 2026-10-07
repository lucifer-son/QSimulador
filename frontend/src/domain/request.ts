import { MODELS } from "./models";
import type { Action, FieldErrors, FieldKey, FormValues, ModelKey, Params } from "./types";

/** Converte texto em número. Aceita vírgula decimal; rejeita vazio e lixo (ex.: "0x10"). */
export function parseNumber(text: string): number {
  const t = text.trim().replace(",", ".");
  if (!/^[+-]?(\d+\.?\d*|\.\d+)([eE][+-]?\d+)?$/.test(t)) return NaN;
  return Number(t);
}

export type ParseResult =
  | { ok: true; params: Params }
  | { ok: false; errors: FieldErrors };

/**
 * Valida só o formato dos campos (número, inteiro). As regras do domínio
 * (λ < μ, capacity ≥ servers, limites...) ficam na API.
 */
export function parseForm(values: FormValues, model: ModelKey, action: Action): ParseResult {
  const info = MODELS[model];
  const errors: FieldErrors = {};

  const read = (field: FieldKey, integer = false): number | undefined => {
    const n = parseNumber(values[field]);
    if (!Number.isFinite(n)) {
      errors[field] = "Informe um número.";
      return undefined;
    }
    if (integer && !Number.isInteger(n)) {
      errors[field] = "Informe um número inteiro.";
      return undefined;
    }
    return n;
  };

  const lambda = read("lambda");
  const mu = read("mu");
  const servers = info.usesServers ? read("servers", true) : undefined;
  const capacity = info.usesCapacity ? read("capacity", true) : undefined;

  let simulationTime: number | undefined;
  let replications: number | undefined;
  let warmupTime: number | undefined;
  let seed: number | undefined;
  if (action !== "calculate") {
    simulationTime = read("simulationTime");
    replications = read("replications", true);
    warmupTime = read("warmupTime");
    if (values.seed.trim() !== "") seed = read("seed", true);
  }

  if (Object.keys(errors).length > 0) return { ok: false, errors };
  return {
    ok: true,
    params: { lambda: lambda!, mu: mu!, servers, capacity, simulationTime, replications, warmupTime, seed },
  };
}

/** Corpo JSON da requisição, com os nomes de campo da API. */
export function buildBody(model: ModelKey, params: Params, action: Action): Record<string, number> {
  const info = MODELS[model];
  const body: Record<string, number> = { lambda: params.lambda, mu: params.mu };
  if (info.usesServers) body.servers = params.servers!;
  if (info.usesCapacity) body.capacity = params.capacity!;
  if (action !== "calculate") {
    body.simulation_time = params.simulationTime!;
    body.replications = params.replications!;
    body.warmup_time = params.warmupTime!;
    if (params.seed !== undefined) body.seed = params.seed;
  }
  return body;
}
