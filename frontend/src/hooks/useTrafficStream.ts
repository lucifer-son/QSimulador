import { useCallback, useState } from "react";
import { useExperiment } from "./useExperiment";

export interface StreamProgress<P> { completed: number; total: number; partial: P[] }

/**
 * Executa uma chamada que chega aos poucos (comparação de planos, varredura): além do estado final, guarda o
 * progresso e o que já chegou, para a tela mostrar as linhas prontas enquanto as outras ainda rodam.
 */
export function useTrafficStream<R, P>() {
  const experiment = useExperiment<R>();
  const [progress, setProgress] = useState<StreamProgress<P>>({ completed: 0, total: 0, partial: [] });
  const { run: runExperiment } = experiment;

  const run = useCallback(
    (call: (signal: AbortSignal, push: (completed: number, total: number, item?: P) => void) => Promise<R>) => {
      setProgress({ completed: 0, total: 0, partial: [] });
      return runExperiment((signal) =>
        call(signal, (completed, total, item) =>
          setProgress((p) => ({ completed, total, partial: item === undefined ? p.partial : [...p.partial, item] }))));
    },
    [runExperiment],
  );

  return { state: experiment.state, cancel: experiment.cancel, run, progress };
}
