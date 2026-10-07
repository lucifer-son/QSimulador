import type { ReactNode } from "react";
import type { RunRow, ViewResult } from "../domain/types";

interface Props {
  result: ViewResult;
  runsStatus: "idle" | "loading" | "error";
  onLoadRuns: () => void;
  children: (runs: RunRow[]) => ReactNode;
}

/** As abas Gráficos e Réplicas precisam das réplicas individuais, que o /compare não devolve. */
export function RunsGate({ result, runsStatus, onLoadRuns, children }: Props) {
  if (result.action === "calculate") {
    return <p className="empty-note">Disponível depois de Comparar ou Só simular.</p>;
  }
  if (result.runs) return <>{children(result.runs)}</>;
  const loading = runsStatus === "loading";
  return (
    <div className="block">
      <p>
        A comparação não traz as réplicas individuais. Repetir a simulação com a mesma semente
        ({result.seed}) gera exatamente as mesmas réplicas.
      </p>
      <button type="button" className="btn" onClick={onLoadRuns} disabled={loading}>
        {loading ? "Carregando…" : "Carregar réplicas"}
      </button>
      {runsStatus === "error" && (
        <p className="field-error" role="alert">Não foi possível carregar as réplicas. Tente de novo.</p>
      )}
    </div>
  );
}
