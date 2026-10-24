import { useCallback, useRef, useState } from "react";
import { ApiError } from "../api/client";
import {
  streamScenarios, type MultipleComparison, type ScenarioRow, type ScenarioSettings, type ScenariosResult,
} from "../api/scenarios";

/** O que já chegou do fluxo: a tela mostra as linhas prontas enquanto as outras ainda rodam. */
export interface PartialScenarios {
  settings: ScenarioSettings;
  multiple_comparison: MultipleComparison;
  base: ScenarioRow | null;
  scenarios: ScenarioRow[];
}

export type ScenarioRunState =
  | { status: "idle" }
  | { status: "loading"; startedAt: number; completed: number; total: number; partial: PartialScenarios | null }
  | { status: "error"; error: ApiError }
  | { status: "success"; result: ScenariosResult };

/** Executa a comparação lendo o NDJSON, com progresso e cancelamento (uma nova execução cancela a anterior). */
export function useScenarioRun() {
  const [state, setState] = useState<ScenarioRunState>({ status: "idle" });
  const controller = useRef<AbortController | null>(null);

  const run = useCallback(async (body: unknown) => {
    controller.current?.abort();
    const mine = new AbortController();
    controller.current = mine;
    const current = () => controller.current === mine;
    setState({ status: "loading", startedAt: Date.now(), completed: 0, total: 0, partial: null });

    let partial: PartialScenarios | null = null;
    let final: ScenariosResult | null = null;
    const startedAt = Date.now();
    const publish = (completed: number, total: number) => {
      if (current()) setState({ status: "loading", startedAt, completed, total, partial });
    };
    try {
      await streamScenarios(body, (event) => {
        if (event.type === "start" && event.settings && event.multiple_comparison) {
          partial = { settings: event.settings, multiple_comparison: event.multiple_comparison, base: null, scenarios: [] };
          publish(0, event.total ?? 0);
        } else if ((event.type === "base" || event.type === "scenario") && event.scenario && partial) {
          partial = event.type === "base"
            ? { ...partial, base: event.scenario }
            : { ...partial, scenarios: [...partial.scenarios, event.scenario] };
          publish(event.completed ?? 0, event.total ?? 0);
        } else if (event.type === "done" && event.result) {
          final = event.result;
        }
      }, mine.signal);
      if (!current()) return;
      if (final) setState({ status: "success", result: final });
      else setState({ status: "error", error: new ApiError("http", "A comparação terminou sem resultado.") });
    } catch (e) {
      if (!current()) return;
      const error = e instanceof ApiError ? e : new ApiError("http", "Erro inesperado.");
      setState(error.code === "aborted" ? { status: "idle" } : { status: "error", error });
    }
  }, []);

  const cancel = useCallback(() => controller.current?.abort(), []);
  return { state, run, cancel };
}
