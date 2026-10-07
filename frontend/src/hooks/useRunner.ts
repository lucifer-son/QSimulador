import { useCallback, useRef, useState } from "react";
import { ApiError } from "../api/client";
import { fetchRuns, runAction } from "../api/actions";
import type { Action, ModelKey, Params, ViewResult } from "../domain/types";

export type RunnerState =
  | { status: "idle" }
  | { status: "loading"; action: Action; startedAt: number }
  | { status: "error"; action: Action; error: ApiError }
  | { status: "success"; result: ViewResult; runs: "idle" | "loading" | "error" };

/** Executa as ações da API, com cancelamento e carga sob demanda das réplicas. */
export function useRunner() {
  const [state, setState] = useState<RunnerState>({ status: "idle" });
  const controller = useRef<AbortController | null>(null);

  const run = useCallback(async (model: ModelKey, action: Action, params: Params) => {
    controller.current?.abort();
    const mine = new AbortController();
    controller.current = mine;
    setState({ status: "loading", action, startedAt: Date.now() });
    try {
      const result = await runAction(model, action, params, mine.signal);
      if (controller.current !== mine) return;
      setState({ status: "success", result, runs: "idle" });
    } catch (e) {
      if (controller.current !== mine) return;
      const error = e instanceof ApiError ? e : new ApiError("http", "Erro inesperado.");
      setState(error.code === "aborted" ? { status: "idle" } : { status: "error", action, error });
    }
  }, []);

  const cancel = useCallback(() => controller.current?.abort(), []);

  const loadRuns = useCallback(async () => {
    if (state.status !== "success" || state.result.runs) return;
    const base = state.result;
    setState({ status: "success", result: base, runs: "loading" });
    try {
      const runs = await fetchRuns(base);
      setState((current) =>
        current.status === "success" && current.result === base
          ? { status: "success", result: { ...base, runs }, runs: "idle" }
          : current,
      );
    } catch {
      setState((current) =>
        current.status === "success" && current.result === base
          ? { status: "success", result: base, runs: "error" }
          : current,
      );
    }
  }, [state]);

  return { state, run, cancel, loadRuns };
}
