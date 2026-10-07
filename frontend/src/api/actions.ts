import { MODELS } from "../domain/models";
import { buildBody } from "../domain/request";
import type { Action, ModelKey, Params, RunRow, ViewResult } from "../domain/types";
import { postJson } from "./client";
import {
  fromCalculate, fromCompare, fromSimulate,
  type CalculateResponse, type CompareResponse, type SimulateResponse,
} from "./mappers";

export async function runAction(
  model: ModelKey,
  action: Action,
  params: Params,
  signal?: AbortSignal,
): Promise<ViewResult> {
  const url = `${MODELS[model].path}/${action}`;
  const body = buildBody(model, params, action);
  switch (action) {
    case "calculate":
      return fromCalculate(model, params, await postJson<CalculateResponse>(url, body, signal));
    case "simulate":
      return fromSimulate(model, params, await postJson<SimulateResponse>(url, body, signal));
    case "compare":
      return fromCompare(model, params, await postJson<CompareResponse>(url, body, signal));
  }
}

/**
 * O /compare não devolve as réplicas individuais. Repetir a simulação com a
 * mesma semente reproduz exatamente as mesmas réplicas (resultado determinístico).
 */
export async function fetchRuns(result: ViewResult, signal?: AbortSignal): Promise<RunRow[]> {
  const params: Params = { ...result.params, seed: result.seed };
  const simulated = await runAction(result.modelKey, "simulate", params, signal);
  return simulated.runs ?? [];
}
