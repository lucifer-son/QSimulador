import { useCallback, useRef, useState } from "react";
import { ApiError } from "../api/client";

export type ExperimentState<T> =
  | { status: "idle" }
  | { status: "loading"; startedAt: number }
  | { status: "error"; error: ApiError }
  | { status: "success"; result: T };

/** Executa uma chamada de experimento, com cancelamento (uma nova execução cancela a anterior). */
export function useExperiment<T>() {
  const [state, setState] = useState<ExperimentState<T>>({ status: "idle" });
  const controller = useRef<AbortController | null>(null);

  const run = useCallback(async (call: (signal: AbortSignal) => Promise<T>) => {
    controller.current?.abort();
    const mine = new AbortController();
    controller.current = mine;
    setState({ status: "loading", startedAt: Date.now() });
    try {
      const result = await call(mine.signal);
      if (controller.current === mine) setState({ status: "success", result });
    } catch (e) {
      if (controller.current !== mine) return;
      const error = e instanceof ApiError ? e : new ApiError("http", "Erro inesperado.");
      setState(error.code === "aborted" ? { status: "idle" } : { status: "error", error });
    }
  }, []);

  const cancel = useCallback(() => controller.current?.abort(), []);

  return { state, run, cancel };
}
