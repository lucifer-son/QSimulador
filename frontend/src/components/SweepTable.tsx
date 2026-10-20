import { IconCheck, IconX } from "@tabler/icons-react";
import type { SweepResponse } from "../api/experiments";
import { formatMetric, formatNumber, formatPercentNumber } from "../domain/format";
import { VARIABLE_INFO, type SweepVariable } from "../domain/experiments";
import { METRIC_INFO } from "../domain/metrics";
import { MODELS } from "../domain/models";
import type { ExperimentModelKey, MetricName } from "../domain/types";

const STATUS_LABEL = { unstable: "instável", invalid: "inválido" } as const;

/** Tabela com todas as métricas de cada ponto (RF-38). Com simulação, mostra a média simulada embaixo. */
export function SweepTable({ result }: { result: SweepResponse }) {
  const model = result.model as ExperimentModelKey;
  const variable = result.variable as SweepVariable;
  const firstOk = result.points.find((p) => p.metrics);
  const names: MetricName[] = MODELS[model].metrics.filter((n) => firstOk?.metrics && n in firstOk.metrics);
  const simulated = result.simulation !== null;

  return (
    <div className="table-wrap">
      <table className="table">
        <caption className="sr-only">
          Métricas do modelo variando {VARIABLE_INFO[variable].label}
          {simulated ? ", com a média simulada de cada ponto" : ""}
        </caption>
        <thead>
          <tr>
            <th scope="col">{VARIABLE_INFO[variable].label}</th>
            <th scope="col" className="num">{model === "mg1" ? "λ·E[S]" : "λ/(c·μ)"}</th>
            <th scope="col">Situação</th>
            {names.map((n) => <th key={n} scope="col" className="num">{METRIC_INFO[n].short}</th>)}
          </tr>
        </thead>
        <tbody>
          {result.points.map((p) => (
            <tr key={p.value}>
              <th scope="row">{formatNumber(p.value)}</th>
              <td className="num">{formatPercentNumber(p.offered_utilization * 100, 1)}</td>
              <td>
                {p.status === "ok" ? (
                  <span className="tag tag-ok"><IconCheck size={14} aria-hidden="true" />estável</span>
                ) : (
                  <span className="tag tag-bad" title={p.message ?? undefined}>
                    <IconX size={14} aria-hidden="true" />{STATUS_LABEL[p.status]}
                  </span>
                )}
              </td>
              {names.map((n) => (
                <td key={n} className="num">
                  {p.metrics ? formatMetric(n, p.metrics[n], { unit: false }) : "—"}
                  {p.simulation?.[n] && (
                    <small className="cell-sim">sim. {formatMetric(n, p.simulation[n].mean, { unit: false })}</small>
                  )}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
