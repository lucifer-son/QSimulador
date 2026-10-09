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

/**
 * Decide em quais campos do formulário um erro da API deve aparecer, a partir do
 * `fields` que a própria API devolve (nos erros de formato e nos de regra).
 */
export function fieldErrorsFromApi(error: ApiError): FieldErrors {
  const out: FieldErrors = {};
  for (const issue of error.fields ?? []) {
    const key = API_TO_FORM[issue.field];
    if (!key) continue;
    if (error.code === "invalid_request") out[key] = "Valor inválido para este campo.";
    else if (error.code === "insufficient_sample") out[key] = "Aumente o tempo simulado.";
    else out[key] = issue.message;
  }
  return out;
}
