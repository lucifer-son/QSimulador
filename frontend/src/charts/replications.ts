import { METRIC_INFO } from "../domain/metrics";
import type { MetricName, MetricRow, RunRow } from "../domain/types";
import type { ThemeColors } from "../hooks/useThemeColors";

export interface ReplicationSeries {
  x: number[];
  y: number[];
  mean?: number;
  analytical?: number;
  scale: number;   // 100 para frações (exibidas em %)
  suffix: string;
}

export function replicationSeries(runs: RunRow[], metric: MetricRow): ReplicationSeries {
  const scale = METRIC_INFO[metric.name].kind === "fraction" ? 100 : 1;
  const name: MetricName = metric.name;
  const valid = runs.filter((r) => r.values[name] !== undefined);
  return {
    x: valid.map((r) => r.index + 1),
    y: valid.map((r) => (r.values[name] as number) * scale),
    mean: metric.simulated === undefined ? undefined : metric.simulated * scale,
    analytical: metric.analytical === undefined ? undefined : metric.analytical * scale,
    scale,
    suffix: scale === 100 ? "%" : "",
  };
}

export function replicationChart(series: ReplicationSeries, colors: ThemeColors) {
  const n = series.x.length;
  const span = [Math.min(...series.x) - 0.5, Math.max(...series.x) + 0.5];
  const line = (name: string, value: number, color: string, dash: string) => ({
    type: "scatter", mode: "lines", name, x: span, y: [value, value],
    line: { color, width: 2, dash }, hoverinfo: "skip",
  });
  const data: object[] = [
    {
      type: "scatter", mode: "markers", name: "Réplicas",
      x: series.x, y: series.y, marker: { color: colors.textSecondary, size: 8 },
      hovertemplate: "Réplica %{x}: %{y:.4g}<extra></extra>",
    },
  ];
  if (series.mean !== undefined) data.push(line("Média simulada", series.mean, colors.accent, "dash"));
  if (series.analytical !== undefined) data.push(line("Analítico", series.analytical, colors.danger, "solid"));
  const layout = {
    height: 320,
    margin: { l: 60, r: 20, t: 10, b: 90 },
    separators: ",.",
    paper_bgcolor: "rgba(0,0,0,0)",
    plot_bgcolor: "rgba(0,0,0,0)",
    font: { color: colors.textSecondary, size: 12 },
    dragmode: false,
    legend: { orientation: "h", y: -0.3 },
    xaxis: {
      title: { text: "Réplica" }, dtick: n > 12 ? undefined : 1, range: span,
      gridcolor: colors.border, fixedrange: true,
    },
    yaxis: { ticksuffix: series.suffix, gridcolor: colors.border, fixedrange: true },
  };
  return { data, layout };
}
