import { useCallback, useRef, useState } from "react";
import { ApiError } from "../api/client";
import { streamFit, type FitCandidate, type FitResult } from "../api/analysis";

export type FitRunState =
  | { status: "idle" }
  | { status: "loading"; startedAt: number; completed: number; total: number; bootstrap: number; candidates: FitCandidate[] }
  | { status: "error"; error: ApiError }
  | { status: "success"; result: FitResult; request: Record<string, unknown> };

/** Executa o ajuste lendo o NDJSON: mostra o progresso por candidata e deixa cancelar (uma nova execução cancela a anterior). */
export function useFitRun() {
  const [state, setState] = useState<FitRunState>({ status: "idle" });
  const controller = useRef<AbortController | null>(null);

  const run = useCallback(async (body: Record<string, unknown>) => {
    controller.current?.abort();
    const mine = new AbortController();
    controller.current = mine;
    const current = () => controller.current === mine;
    const startedAt = Date.now();
    let total = 0;
    let bootstrap = 0;
    let candidates: FitCandidate[] = [];
    let final: FitResult | null = null;
    setState({ status: "loading", startedAt, completed: 0, total, bootstrap, candidates });
    try {
      await streamFit(body, (event) => {
        if (event.type === "start") {
          total = event.total ?? 0;
          bootstrap = event.bootstrap ?? 0;
        } else if (event.type === "candidate" && event.candidate) {
          candidates = [...candidates, event.candidate];
        } else if (event.type === "done" && event.result) {
          final = event.result;
        }
        if (current() && event.type !== "done") {
          setState({ status: "loading", startedAt, completed: candidates.length, total, bootstrap, candidates });
        }
      }, mine.signal);
      if (!current()) return;
      if (final) setState({ status: "success", result: final, request: body });
      else setState({ status: "error", error: new ApiError("http", "O ajuste terminou sem resultado.") });
    } catch (e) {
      if (!current()) return;
      const error = e instanceof ApiError ? e : new ApiError("http", "Erro inesperado.");
      setState(error.code === "aborted" ? { status: "idle" } : { status: "error", error });
    }
  }, []);

  const cancel = useCallback(() => controller.current?.abort(), []);
  return { state, run, cancel };
}
