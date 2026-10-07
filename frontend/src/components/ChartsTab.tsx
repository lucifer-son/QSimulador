import { useMemo, useState } from "react";
import { replicationChart, replicationSeries } from "../charts/replications";
import type { MetricName, ViewResult } from "../domain/types";
import { useThemeColors } from "../hooks/useThemeColors";
import { metricTitle } from "./MetricsTable";
import { PlotlyChart } from "./PlotlyChart";
import { RunsGate } from "./RunsGate";

interface Props {
  result: ViewResult;
  runsStatus: "idle" | "loading" | "error";
  onLoadRuns: () => void;
}

export function ChartsTab({ result, runsStatus, onLoadRuns }: Props) {
  const colors = useThemeColors();
  const [selected, setSelected] = useState<MetricName>("rho");
  const metric = result.metrics.find((m) => m.name === selected) ?? result.metrics[0];

  return (
    <RunsGate result={result} runsStatus={runsStatus} onLoadRuns={onLoadRuns}>
      {(runs) => <ReplicationsPlot runs={runs} metric={metric} colors={colors} onSelect={setSelected} result={result} />}
    </RunsGate>
  );
}

function ReplicationsPlot({
  runs, metric, colors, onSelect, result,
}: {
  runs: NonNullable<ViewResult["runs"]>;
  metric: ViewResult["metrics"][number];
  colors: ReturnType<typeof useThemeColors>;
  onSelect: (name: MetricName) => void;
  result: ViewResult;
}) {
  const chart = useMemo(
    () => replicationChart(replicationSeries(runs, metric), colors),
    [runs, metric, colors],
  );
  return (
    <section className="block">
      <div className="field inline">
        <label htmlFor="chart-metric">Métrica</label>
        <select id="chart-metric" value={metric.name} onChange={(e) => onSelect(e.target.value as MetricName)}>
          {result.metrics.map((m) => (
            <option key={m.name} value={m.name}>{metricTitle(m.name)}</option>
          ))}
        </select>
      </div>
      <p className="sub">Valor de cada réplica, a média simulada e, na comparação, o valor analítico.</p>
      <PlotlyChart
        data={chart.data}
        layout={chart.layout}
        label={`Valor de ${metricTitle(metric.name)} em cada réplica`}
      />
    </section>
  );
}
