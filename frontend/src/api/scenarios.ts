import type { components } from "./schema";
import { ApiError, apiErrorFrom, fetchApi } from "./client";

type S = components["schemas"];

export type ScenariosRequest = S["ScenariosRequest"];
export type ScenarioEvent = S["ScenarioEventOut"];
export type ScenariosResult = S["ScenariosResultOut"];
export type ScenarioRow = S["ScenarioRowOut"];
export type ScenarioMetric = S["ScenarioMetricOut"];
export type ScenarioSummary = S["ScenarioSummaryOut"];
export type ScenarioAlert = S["ScenarioAlertOut"];
export type MultipleComparison = S["ScenarioMultipleComparisonOut"];
export type ScenarioSettings = S["ScenarioSettingsOut"];

const JSON_POST = (body: unknown): RequestInit => ({
  method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body),
});

/**
 * POST /api/scenarios/compare: lê o NDJSON e chama `onEvent` a cada linha completa, na ordem em que
 * o servidor as envia. Cancelar o `signal` fecha a conexão, e o servidor interrompe o que falta.
 * Um evento `error` no meio do fluxo vira ApiError, como os erros que vêm antes do fluxo (422).
 */
export async function streamScenarios(
  body: unknown, onEvent: (event: ScenarioEvent) => void, signal?: AbortSignal,
): Promise<void> {
  const response = await fetchApi("/api/scenarios/compare", JSON_POST(body), signal);
  if (!response.ok) throw await apiErrorFrom(response);
  if (!response.body) throw new ApiError("http", "A API não enviou o fluxo de resultados.");

  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let pending = "";
  const flush = (line: string) => {
    if (!line.trim()) return;
    const event = JSON.parse(line) as ScenarioEvent;
    if (event.type === "error") {
      const code = event.code === "insufficient_sample" ? "insufficient_sample" : "http";
      throw new ApiError(code, event.message ?? "Falha ao comparar os cenários.");
    }
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

/** POST /api/scenarios/export.csv: refaz a comparação (mesmo corpo e semente) e devolve o CSV. */
export async function exportScenariosCsv(body: unknown, signal?: AbortSignal): Promise<Blob> {
  const response = await fetchApi("/api/scenarios/export.csv", JSON_POST(body), signal);
  if (!response.ok) throw await apiErrorFrom(response);
  return response.blob();
}
