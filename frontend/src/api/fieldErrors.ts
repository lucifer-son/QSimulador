import type { FieldErrors, FieldKey } from "../domain/types";
import type { ApiError } from "./client";

const API_TO_FORM: Record<string, FieldKey> = {
  lambda: "lambda",
  mu: "mu",
  servers: "servers",
  capacity: "capacity",
  simulation_time: "simulationTime",
  replications: "replications",
  warmup_time: "warmupTime",
  seed: "seed",
};

// As mensagens de domínio começam pelo nome do campo (ex.: "capacity deve ser...").
const MESSAGE_PREFIXES: [RegExp, FieldKey][] = [
  [/^λ/, "lambda"],
  [/^μ/, "mu"],
  [/^servers\b/, "servers"],
  [/^capacity\b/, "capacity"],
  [/^simulation_time\b/, "simulationTime"],
  [/^replications\b/, "replications"],
  [/^warmup_time\b/, "warmupTime"],
  [/^seed\b/, "seed"],
];

/** Decide em quais campos do formulário um erro da API deve aparecer. */
export function fieldErrorsFromApi(error: ApiError): FieldErrors {
  const out: FieldErrors = {};
  if (error.code === "invalid_request") {
    for (const issue of error.fields ?? []) {
      const key = API_TO_FORM[issue.field];
      if (key) out[key] = "Valor inválido para este campo.";
    }
    return out;
  }
  if (error.code === "unstable_system") {
    out.lambda = error.message;
    return out;
  }
  if (error.code === "insufficient_sample") {
    out.simulationTime = "Aumente o tempo simulado.";
    return out;
  }
  if (error.code === "invalid_parameter") {
    const match = MESSAGE_PREFIXES.find(([re]) => re.test(error.message));
    if (match) out[match[1]] = error.message;
  }
  return out;
}
