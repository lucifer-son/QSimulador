import { METRIC_INFO, metricAxisTitle } from "../domain/metrics";
import type { MetricName, MetricRow, RunRow } from "../domain/types";
import type { ThemeColors } from "../hooks/useThemeColors";

export interface ReplicationSeries {
  x: number[];
  y: number[];
  mean?: number;
  analytical?: number;
  ci?: { low: number; high: number }; // IC da média simulada, na mesma escala
  yTitle: string;
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
    ci: typeof metric.ciLow === "number" && typeof metric.ciHigh === "number"
      ? { low: metric.ciLow * scale, high: metric.ciHigh * scale }
      : undefined,
    yTitle: metricAxisTitle(name),
    scale,
    suffix: scale === 100 ? "%" : "",
  };
}

/** Aplica transparência a uma cor #rrggbb (o Plotly não aceita alfa em hex). */
export function withAlpha(color: string, alpha: number): string {
  const m = /^#([0-9a-f]{2})([0-9a-f]{2})([0-9a-f]{2})$/i.exec(color.trim());
  if (!m) return `rgba(120,120,120,${alpha})`;
  return `rgba(${parseInt(m[1], 16)},${parseInt(m[2], 16)},${parseInt(m[3], 16)},${alpha})`;
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
      x: series.x, y: series.y, marker: { color: colors.textSecondary, size: 8, symbol: "circle" },
      hovertemplate: "Réplica %{x}: %{y:.4g}<extra></extra>",
    },
  ];
  if (series.ci) {
    const { low, high } = series.ci;
    data.push({
      type: "scatter", mode: "lines", name: "Intervalo de confiança", fill: "toself",
      x: [span[0], span[1], span[1], span[0]], y: [low, low, high, high],
      line: { width: 0 }, fillcolor: withAlpha(colors.accent, 0.18), hoverinfo: "skip",
    });
  }
  if (series.mean !== undefined) data.push(line("Média simulada", series.mean, colors.accent, "dash"));
  if (series.analytical !== undefined) data.push(line("Analítico", series.analytical, colors.danger, "solid"));
  const layout = {
    height: 320,
    margin: { l: 70, r: 20, t: 10, b: 90 },
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
    yaxis: {
      title: { text: series.yTitle }, automargin: true, ticksuffix: series.suffix,
      gridcolor: colors.border, fixedrange: true,
    },
  };
  return { data, layout };
}
