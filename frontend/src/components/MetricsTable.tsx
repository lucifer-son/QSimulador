import { IconCheck, IconX } from "@tabler/icons-react";
import { METRIC_INFO } from "../domain/metrics";
import { formatMetric, formatPercentNumber } from "../domain/format";
import type { MetricName, ViewResult } from "../domain/types";

export function metricTitle(name: MetricName): string {
  const { label, short } = METRIC_INFO[name];
  return label === short ? label : `${label} (${short})`;
}

export function MetricsTable({ result }: { result: ViewResult }) {
  const compare = result.action === "compare";
  const simulate = result.action === "simulate";
  const precise = { precise: true };
  const bare = { precise: true, unit: false };

  return (
    <div className="table-wrap">
      <table className="table">
        <caption className="sr-only">Métricas do modelo {result.modelLabel}</caption>
        <thead>
          <tr>
            <th scope="col">Métrica</th>
            {result.action === "calculate" && <th scope="col" className="num">Valor</th>}
            {compare && <th scope="col" className="num">Analítico</th>}
            {(compare || simulate) && <th scope="col" className="num">Simulação</th>}
            {(compare || simulate) && <th scope="col" className="num">IC</th>}
            {simulate && <th scope="col" className="num">Desvio padrão</th>}
            {compare && <th scope="col" className="num">Erro</th>}
            {compare && <th scope="col">No IC?</th>}
          </tr>
        </thead>
        <tbody>
          {result.metrics.map((m) => (
            <tr key={m.name}>
              <th scope="row">{metricTitle(m.name)}</th>
              {result.action === "calculate" && (
                <td className="num">{formatMetric(m.name, m.analytical!, precise)}</td>
              )}
              {compare && <td className="num">{formatMetric(m.name, m.analytical!, precise)}</td>}
              {(compare || simulate) && <td className="num">{formatMetric(m.name, m.simulated!, precise)}</td>}
              {(compare || simulate) && (
                <td className="num">
                  {m.ciLow != null && m.ciHigh != null
                    ? `[${formatMetric(m.name, m.ciLow, bare)}; ${formatMetric(m.name, m.ciHigh, bare)}]`
                    : "—"}
                </td>
              )}
              {simulate && (
                <td className="num">{m.std != null ? formatMetric(m.name, m.std, bare) : "—"}</td>
              )}
              {compare && (
                <td className="num">{m.errorPct != null ? formatPercentNumber(m.errorPct) : "—"}</td>
              )}
              {compare && (
                <td>
                  {m.withinCi === true && <span className="tag tag-ok"><IconCheck size={14} aria-hidden="true" />sim</span>}
                  {m.withinCi === false && <span className="tag tag-bad"><IconX size={14} aria-hidden="true" />não</span>}
                  {m.withinCi == null && "—"}
                </td>
              )}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
