import { METRIC_INFO } from "../domain/metrics";
import { formatSignedPercent } from "../domain/format";
import type { MetricName, MetricRow } from "../domain/types";
import type { ThemeColors } from "../hooks/useThemeColors";

export interface DeviationPoint {
  name: MetricName;
  label: string;
  diff: number; // diferença da média simulada em relação ao analítico (%)
  lo: number;   // limite inferior do IC (%)
  hi: number;   // limite superior do IC (%)
  within: boolean;
}

export interface DeviationData {
  points: DeviationPoint[];
  /** Métricas sem diferença relativa possível (valor analítico = 0). */
  omitted: MetricName[];
}

/** Põe todas as métricas numa escala só: a diferença percentual em relação ao analítico. */
export function deviationData(metrics: MetricRow[]): DeviationData {
  const points: DeviationPoint[] = [];
  const omitted: MetricName[] = [];
  for (const m of metrics) {
    const { analytical: a, simulated: s, ciLow, ciHigh } = m;
    if (a === undefined || s === undefined || ciLow == null || ciHigh == null) continue;
    if (a === 0) {
      omitted.push(m.name);
      continue;
    }
    const pct = (v: number) => ((v - a) / Math.abs(a)) * 100;
    points.push({
      name: m.name,
      label: METRIC_INFO[m.name].short,
      diff: pct(s),
      lo: pct(ciLow),
      hi: pct(ciHigh),
      within: a >= ciLow && a <= ciHigh,
    });
  }
  return { points, omitted };
}

function trace(points: DeviationPoint[], name: string, color: string, symbol: string) {
  return {
    type: "scatter",
    mode: "markers",
    name,
    x: points.map((p) => p.diff),
    y: points.map((p) => p.label),
    text: points.map((p) => `IC: ${formatSignedPercent(p.lo)} a ${formatSignedPercent(p.hi)}`),
    marker: { color, size: 10, symbol },
    error_x: {
      type: "data",
      symmetric: false,
      array: points.map((p) => p.hi - p.diff),
      arrayminus: points.map((p) => p.diff - p.lo),
      color,
      thickness: 2,
      width: 4,
    },
    hovertemplate: "%{y}: %{x:+.2f}%<br>%{text}<extra></extra>",
  };
}

export function deviationChart(points: DeviationPoint[], colors: ThemeColors) {
  const inside = points.filter((p) => p.within);
  const outside = points.filter((p) => !p.within);
  const maxAbs = Math.max(0.5, ...points.flatMap((p) => [Math.abs(p.lo), Math.abs(p.hi)])) * 1.15;
  const data = [
    ...(inside.length ? [trace(inside, "Analítico dentro do IC", colors.accent, "circle")] : []),
    ...(outside.length ? [trace(outside, "Analítico fora do IC", colors.danger, "diamond")] : []),
  ];
  const layout = {
    height: 120 + 30 * points.length,
    margin: { l: 90, r: 20, t: 10, b: 90 },
    separators: ",.",
    paper_bgcolor: "rgba(0,0,0,0)",
    plot_bgcolor: "rgba(0,0,0,0)",
    font: { color: colors.textSecondary, size: 12 },
    dragmode: false,
    showlegend: true,
    legend: { orientation: "h", y: -0.4 },
    xaxis: {
      title: { text: "Diferença em relação ao analítico (%)" },
      range: [-maxAbs, maxAbs],
      ticksuffix: "%",
      zeroline: true,
      zerolinecolor: colors.textMuted,
      zerolinewidth: 1.5,
      gridcolor: colors.border,
      fixedrange: true,
    },
    yaxis: { title: { text: "Métrica" }, automargin: true, autorange: "reversed", gridcolor: colors.border, fixedrange: true },
  };
  return { data, layout };
}
