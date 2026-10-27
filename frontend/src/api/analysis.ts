import type { components } from "./schema";
import { ApiError, apiErrorFrom, fetchApi, postJson } from "./client";

type S = components["schemas"];

export type DistributionRequest = S["AnalysisDistributionRequest"];
export type DistributionResponse = S["AnalysisDistributionResponse"];
export type StatesOut = S["AnalysisStatesOut"];
export type WaitTailOut = S["AnalysisWaitTailOut"];
export type WaitSimulationOut = S["AnalysisWaitSimulationOut"];
export type SensitivityRequest = S["AnalysisSensitivityRequest"];
export type SensitivityCurve = S["AnalysisSensitivityResponse"];
export type CurvePoint = S["AnalysisCurvePointOut"];
export type FitRequest = S["AnalysisFitRequest"];
export type FitEvent = S["AnalysisFitEventOut"];
export type FitResult = S["AnalysisFitResultOut"];
export type FitCandidate = S["AnalysisFitCandidateOut"];
export type ModelSuggestion = S["AnalysisModelSuggestionOut"];

/** POST /api/analysis/distribution: P(n) analítica e P(Wq > t) (fórmula fechada ou histograma da simulação). */
export const fetchDistribution = (body: DistributionRequest | Record<string, unknown>, signal?: AbortSignal) =>
  postJson<DistributionResponse>("/api/analysis/distribution", body, signal);

/** POST /api/analysis/sensitivity: curva Wq × λ ao redor da configuração atual. */
export const fetchSensitivityCurve = (body: SensitivityRequest | Record<string, unknown>, signal?: AbortSignal) =>
  postJson<SensitivityCurve>("/api/analysis/sensitivity", body, signal);

/**
 * POST /api/analysis/fit: lê o NDJSON e chama `onEvent` a cada linha completa. Os erros de validação (422) e o
 * 413 chegam antes do fluxo e viram ApiError; um evento `error` no meio do fluxo também. Cancelar o `signal`
 * fecha a conexão e o servidor para entre uma candidata e outra.
 */
export async function streamFit(
  body: FitRequest | Record<string, unknown>, onEvent: (event: FitEvent) => void, signal?: AbortSignal,
): Promise<void> {
  const response = await fetchApi("/api/analysis/fit", {
    method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body),
  }, signal);
  if (!response.ok) throw await apiErrorFrom(response);
  if (!response.body) throw new ApiError("http", "A API não enviou o fluxo de resultados.");

  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let pending = "";
  const flush = (line: string) => {
    if (!line.trim()) return;
    const event = JSON.parse(line) as FitEvent;
    if (event.type === "error") throw new ApiError("http", event.message ?? "Falha ao ajustar a distribuição.");
    onEvent(event);
  };
  try {
    for (;;) {
      const { done, value } = await reader.read();
      if (done) break;
      pending += decoder.decode(value, { stream: true });
      const lines = pending.split("\n");
      pending = lines.pop() ?? "";
      lines.forEach(flush);
    }
    pending += decoder.decode();
    flush(pending);
  } catch (error) {
    if (error instanceof ApiError) throw error;
    const aborted = signal?.aborted || (error instanceof DOMException && error.name === "AbortError");
    if (aborted) throw new ApiError("aborted", "Execução cancelada.");
    throw new ApiError("network", "A conexão com a API foi interrompida.");
  }
}
