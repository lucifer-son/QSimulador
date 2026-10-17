import { parseNumber } from "./number";
import { MODELS } from "./models";
import { parseService, serviceMoments } from "./service";
import type { Action, FieldErrors, FieldKey, FormValues, ModelKey, Params } from "./types";

export { parseNumber };

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
  // M/G/1: o serviço é dado pela distribuição (média, forma...), não por μ.
  const service = model === "mg1" ? parseService(values) : null;
  if (service && !service.ok) Object.assign(errors, service.errors);
  const mu = model === "mg1" ? undefined : read("mu");
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
  if (service?.ok) {
    // μ = 1/E[S] só para exibição (título, detalhes): a API devolve o valor efetivo.
    const moments = serviceMoments(service.service.distribution, service.service.values);
    return {
      ok: true,
      params: {
        lambda: lambda!, mu: moments?.mu ?? 0, servers, capacity,
        simulationTime, replications, warmupTime, seed, service: service.service,
      },
    };
  }
  return {
    ok: true,
    params: { lambda: lambda!, mu: mu!, servers, capacity, simulationTime, replications, warmupTime, seed },
  };
}

/** Corpo JSON da requisição, com os nomes de campo da API. */
export function buildBody(model: ModelKey, params: Params, action: Action): Record<string, number | string> {
  const info = MODELS[model];
  const body: Record<string, number | string> =
    model === "mg1" ? { lambda: params.lambda, distribution: params.service!.distribution, ...params.service!.values }
      : { lambda: params.lambda, mu: params.mu };
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
