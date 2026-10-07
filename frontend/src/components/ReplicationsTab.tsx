import { formatInteger, formatMetric } from "../domain/format";
import type { ViewResult } from "../domain/types";
import { metricTitle } from "./MetricsTable";
import { RunsGate } from "./RunsGate";

interface Props {
  result: ViewResult;
  runsStatus: "idle" | "loading" | "error";
  onLoadRuns: () => void;
}

export function ReplicationsTab({ result, runsStatus, onLoadRuns }: Props) {
  return (
    <RunsGate result={result} runsStatus={runsStatus} onLoadRuns={onLoadRuns}>
      {(runs) => (
        <div className="table-wrap">
          <table className="table">
            <caption className="sr-only">Métricas de cada réplica</caption>
            <thead>
              <tr>
                <th scope="col">Réplica</th>
                {result.metrics.map((m) => (
                  <th scope="col" className="num" key={m.name} title={metricTitle(m.name)}>
                    {metricTitle(m.name).replace(/^.*\((.*)\)$/, "$1")}
                  </th>
                ))}
                <th scope="col" className="num">Clientes medidos</th>
              </tr>
            </thead>
            <tbody>
              {runs.map((run) => (
                <tr key={run.index}>
                  <th scope="row">{run.index + 1}</th>
                  {result.metrics.map((m) => (
                    <td className="num" key={m.name}>
                      {run.values[m.name] === undefined ? "—" : formatMetric(m.name, run.values[m.name]!, { unit: false })}
                    </td>
                  ))}
                  <td className="num">{formatInteger(run.measuredCustomers)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </RunsGate>
  );
}
