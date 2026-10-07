import { IconAlertTriangle, IconCircleCheck, IconInfoCircle } from "@tabler/icons-react";
import { formatInteger, formatPercentNumber } from "../domain/format";
import type { ViewResult } from "../domain/types";

type Tone = "success" | "warning" | "info";

function verdict(result: ViewResult): { tone: Tone; text: string; detail?: string } {
  const total = result.metrics.length;
  const level = Math.round((result.confidenceLevel ?? 0.95) * 100);

  if (result.action === "calculate") {
    return { tone: "info", text: "Métricas analíticas em regime estacionário." };
  }
  if (result.action === "simulate") {
    return {
      tone: "info",
      text: `Simulação concluída: ${result.replications} réplicas de ${formatInteger(result.simulationTime ?? 0)} s.`,
    };
  }
  const maxError =
    result.maxErrorPct != null ? `Erro relativo máximo: ${formatPercentNumber(result.maxErrorPct)}.` : undefined;
  if (result.allWithinCi === true) {
    return { tone: "success", text: `As ${total} métricas do analítico estão dentro do IC de ${level}%.`, detail: maxError };
  }
  if (result.allWithinCi === false) {
    const outside = result.metrics.filter((m) => m.withinCi === false).length;
    return {
      tone: "warning",
      text: `${outside} de ${total} métricas ficaram fora do IC de ${level}%.`,
      detail:
        "Com várias métricas, é normal uma ou outra sair do intervalo por acaso. " +
        "Confira o erro relativo e, se precisar, aumente o tempo simulado ou as réplicas.",
    };
  }
  return {
    tone: "info",
    text: "Com 1 réplica não há intervalo de confiança.",
    detail: "Use 2 ou mais réplicas para validar a simulação contra o analítico.",
  };
}

const ICONS = { success: IconCircleCheck, warning: IconAlertTriangle, info: IconInfoCircle };

export function VerdictBanner({ result }: { result: ViewResult }) {
  const { tone, text, detail } = verdict(result);
  const Icon = ICONS[tone];
  return (
    <div className={`banner banner-${tone}`} role="status">
      <Icon size={20} aria-hidden="true" />
      <div>
        <div>{text}</div>
        {detail && <div className="banner-detail">{detail}</div>}
      </div>
    </div>
  );
}
