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
  // A API exige pelo menos 2 réplicas, então o veredito sempre existe; este é só um respaldo.
  return { tone: "info", text: "Não foi possível verificar o intervalo de confiança." };
}

const ICONS = { success: IconCircleCheck, warning: IconAlertTriangle, info: IconInfoCircle };

/** M/G/c: diz se a aproximação de Allen–Cunneen é exata neste caso e repete os avisos de faixa. */
export function ApproximationNote({ result }: { result: ViewResult }) {
  const approx = result.approximation;
  if (!approx) return null;
  const tone: Tone = approx.warnings.length > 0 ? "warning" : "info";
  const Icon = ICONS[tone];
  return (
    <div className={`banner banner-${tone}`} role="note">
      <Icon size={20} aria-hidden="true" />
      <div>
        <div>
          {approx.exact
            ? "Aproximação exata neste caso (um servidor ou serviço exponencial)."
            : "Aproximação de Allen–Cunneen: os valores são aproximados, não exatos."}
        </div>
        {approx.warnings.map((w) => <div key={w} className="banner-detail">{w}</div>)}
        {!approx.exact && result.action === "calculate" && (
          <div className="banner-detail">Use Comparar para ver o erro da aproximação contra a simulação.</div>
        )}
      </div>
    </div>
  );
}

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
