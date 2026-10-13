import type { ParameterSensitivity, SweepPoint } from "../api/experiments";
import { formatNumber, formatSignedPercent } from "../domain/format";
import { HIGH_UTILIZATION, VARIABLE_INFO, type SweepVariable } from "../domain/experiments";
import { METRIC_INFO, metricAxisTitle } from "../domain/metrics";
import type { MetricName } from "../domain/types";
import type { ThemeColors } from "../hooks/useThemeColors";
import { withAlpha } from "./replications";

export type XAxis = "value" | "utilization";

/** Frações (ρ, P0, probabilidades) aparecem em %, como no restante da interface. */
export const metricScale = (name: MetricName): number => (METRIC_INFO[name].kind === "fraction" ? 100 : 1);

const BASE_LAYOUT = (colors: ThemeColors) => ({
  height: 360,
  margin: { l: 70, r: 20, t: 10, b: 100 },
  separators: ",.",
  paper_bgcolor: "rgba(0,0,0,0)",
  plot_bgcolor: "rgba(0,0,0,0)",
  font: { color: colors.textSecondary, size: 12 },
  dragmode: false,
  legend: { orientation: "h", y: -0.35 },
});

export function xTitle(variable: SweepVariable, xAxis: XAxis): string {
  if (xAxis === "utilization") return "Carga oferecida λ/(c·μ)";
  const { label, unit } = VARIABLE_INFO[variable];
  return unit ? `${label} (${unit})` : label;
}

function xOf(point: SweepPoint, xAxis: XAxis): number {
  return xAxis === "utilization" ? point.offered_utilization : point.value;
}

export interface Band {
  x0: number;
  x1: number;
  status: "unstable" | "invalid";
}

export interface SweepSeries {
  /** Pontos válidos, em ordem crescente de x. */
  x: number[];
  y: number[];
  /** Subconjunto em alta utilização (λ/cμ ≥ 80%) e ainda estável. */
  high: { x: number[]; y: number[] };
  /** Simulação: média e limites do IC, na mesma escala de y. */
  sim: { x: number[]; y: number[]; low: (number | null)[]; high: (number | null)[] } | null;
  /** Trechos da faixa que não puderam ser calculados. */
  bands: Band[];
  /** Quantos pontos o gráfico não mostra. */
  omitted: number;
}

export function sweepSeries(points: SweepPoint[], metric: MetricName, xAxis: XAxis): SweepSeries {
  const scale = metricScale(metric);
  const sorted = [...points].sort((a, b) => xOf(a, xAxis) - xOf(b, xAxis));
  const valid = sorted.filter((p) => p.status === "ok" && p.metrics && metric in p.metrics);
  const x = valid.map((p) => xOf(p, xAxis));
  const y = valid.map((p) => (p.metrics as Record<string, number>)[metric] * scale);

  const highPts = valid.filter((p) => p.offered_utilization >= HIGH_UTILIZATION);
  const simPts = valid.filter((p) => p.simulation && metric in p.simulation);
  const sim = simPts.length === 0 ? null : {
    x: simPts.map((p) => xOf(p, xAxis)),
    y: simPts.map((p) => p.simulation![metric].mean * scale),
    low: simPts.map((p) => (p.simulation![metric].ci_low == null ? null : p.simulation![metric].ci_low! * scale)),
    high: simPts.map((p) => (p.simulation![metric].ci_high == null ? null : p.simulation![metric].ci_high! * scale)),
  };

  // Faixas sombreadas: sequências de pontos consecutivos com o mesmo status diferente de "ok".
  const xs = sorted.map((p) => xOf(p, xAxis));
  const gap = (i: number) => {
    const d = i > 0 ? xs[i] - xs[i - 1] : xs.length > 1 ? xs[1] - xs[0] : 1;
    return (d || 1) / 2;
  };
  const bands: Band[] = [];
  let i = 0;
  while (i < sorted.length) {
    const status = sorted[i].status;
    if (status === "ok") { i += 1; continue; }
    let j = i;
    while (j + 1 < sorted.length && sorted[j + 1].status === status) j += 1;
    bands.push({
      x0: i === 0 ? xs[0] - gap(0) : (xs[i - 1] + xs[i]) / 2,
      x1: j === sorted.length - 1 ? xs[j] + gap(j) : (xs[j] + xs[j + 1]) / 2,
      status: status as Band["status"],
    });
    i = j + 1;
  }
  return { x, y, high: { x: highPts.map((p) => xOf(p, xAxis)), y: highPts.map((p) => (p.metrics as Record<string, number>)[metric] * scale) }, sim, bands, omitted: sorted.length - valid.length };
}

export const BAND_LABEL: Record<Band["status"], string> = { unstable: "instável", invalid: "inválido" };

export function sweepChart(
  series: SweepSeries, metric: MetricName, variable: SweepVariable, xAxis: XAxis, colors: ThemeColors,
) {
  const suffix = metricScale(metric) === 100 ? "%" : "";
  const data: object[] = [
    {
      type: "scatter", mode: "lines+markers", name: "Analítico", x: series.x, y: series.y,
      line: { color: colors.danger, width: 2 }, marker: { color: colors.danger, size: 6, symbol: "circle" },
      hovertemplate: "%{x:.4g}: %{y:.4g}<extra>Analítico</extra>",
    },
  ];
  if (series.sim) {
    data.push({
      type: "scatter", mode: "markers", name: "Simulação (média e IC)", x: series.sim.x, y: series.sim.y,
      marker: { color: colors.accent, size: 8, symbol: "diamond" },
      error_y: {
        type: "data", symmetric: false, color: colors.accent, thickness: 2, width: 4,
        array: series.sim.high.map((h, k) => (h == null ? 0 : h - series.sim!.y[k])),
        arrayminus: series.sim.low.map((l, k) => (l == null ? 0 : series.sim!.y[k] - l)),
      },
      hovertemplate: "%{x:.4g}: %{y:.4g}<extra>Simulação</extra>",
    });
  }
  if (series.high.x.length > 0) {
    data.push({
      type: "scatter", mode: "markers", name: `Alta utilização (λ/cμ ≥ ${HIGH_UTILIZATION * 100}%)`,
      x: series.high.x, y: series.high.y,
      marker: { color: "rgba(0,0,0,0)", size: 14, symbol: "square-open", line: { color: colors.textSecondary, width: 2 } },
      hoverinfo: "skip",
    });
  }
  const shapes = series.bands.map((b) => ({
    type: "rect", xref: "x", yref: "paper", x0: b.x0, x1: b.x1, y0: 0, y1: 1, layer: "below", line: { width: 0 },
    fillcolor: withAlpha(b.status === "unstable" ? colors.danger : colors.textMuted, 0.14),
  }));
  const annotations = series.bands.map((b) => ({
    x: (b.x0 + b.x1) / 2, xref: "x", y: 1, yref: "paper", yanchor: "top", showarrow: false,
    text: BAND_LABEL[b.status], font: { color: b.status === "unstable" ? colors.danger : colors.textMuted, size: 11 },
  }));
  const layout = {
    ...BASE_LAYOUT(colors),
    shapes, annotations,
    xaxis: {
      title: { text: xTitle(variable, xAxis) }, gridcolor: colors.border, fixedrange: true,
      ...(xAxis === "utilization" ? { tickformat: ".0%" } : {}),
    },
    yaxis: {
      title: { text: metricAxisTitle(metric) }, automargin: true, ticksuffix: suffix,
      gridcolor: colors.border, fixedrange: true, rangemode: "tozero",
    },
  };
  return { data, layout };
}

/** Texto sobre o trecho instável da faixa; null se tudo foi calculado. */
export function describeUnstable(points: SweepPoint[], variable: SweepVariable): string | null {
  const bad = points.filter((p) => p.status !== "ok");
  if (bad.length === 0) return null;
  const values = bad.map((p) => p.value);
  const label = VARIABLE_INFO[variable].label;
  const range = values.length === 1
    ? formatNumber(values[0])
    : `${formatNumber(Math.min(...values))} a ${formatNumber(Math.max(...values))}`;
  const unstable = bad.some((p) => p.status === "unstable");
  const kind = unstable ? "fora do regime estável" : "fora do domínio do modelo";
  return `${bad.length} de ${points.length} pontos ${kind} (${label} de ${range}); não aparecem nas curvas.`;
}

// ---------- comparação de servidores ----------

const SYMBOLS = ["circle", "square", "diamond", "triangle-up", "x", "cross", "star", "hexagon"];
const DASHES = ["solid", "dash", "dot", "dashdot", "solid", "dash", "dot", "dashdot"];

export interface ServerLine { servers: number; x: number[]; y: (number | null)[] }

export function serverLines(
  series: { servers: number; points: SweepPoint[] }[], metric: MetricName,
): ServerLine[] {
  const scale = metricScale(metric);
  return series.map((s) => {
    const sorted = [...s.points].sort((a, b) => a.value - b.value);
    return {
      servers: s.servers,
      x: sorted.map((p) => p.value),
      y: sorted.map((p) => (p.status === "ok" && p.metrics && metric in p.metrics ? p.metrics[metric] * scale : null)),
    };
  });
}

export function serversChart(lines: ServerLine[], metric: MetricName, colors: ThemeColors) {
  const palette = [colors.accent, colors.danger, "#2f9e6b", "#c47f17", "#8e5bd6", "#17a2b8", colors.textSecondary, "#d6479b"];
  const data = lines.map((l, i) => ({
    type: "scatter", mode: "lines+markers", name: `c = ${l.servers}`, x: l.x, y: l.y, connectgaps: false,
    line: { color: palette[i % palette.length], width: 2, dash: DASHES[i % DASHES.length] },
    marker: { color: palette[i % palette.length], size: 7, symbol: SYMBOLS[i % SYMBOLS.length] },
    hovertemplate: `λ = %{x:.4g}: %{y:.4g}<extra>c = ${l.servers}</extra>`,
  }));
  return {
    data,
    layout: {
      ...BASE_LAYOUT(colors),
      xaxis: { title: { text: "Chegadas λ (req/s)" }, gridcolor: colors.border, fixedrange: true },
      yaxis: {
        title: { text: metricAxisTitle(metric) }, automargin: true, gridcolor: colors.border, fixedrange: true,
        ticksuffix: metricScale(metric) === 100 ? "%" : "", rangemode: "tozero",
      },
    },
  };
}

/** Texto por série sobre onde ela deixa de ser estável; vazio se todas foram calculadas. */
export function describeServerLimits(
  series: { servers: number; points: SweepPoint[] }[],
): string[] {
  const out: string[] = [];
  for (const s of series) {
    const sorted = [...s.points].sort((a, b) => a.value - b.value);
    const unstable = sorted.filter((p) => p.status === "unstable");
    const invalid = sorted.filter((p) => p.status === "invalid");
    if (invalid.length === sorted.length && sorted.length > 0) {
      out.push(`c = ${s.servers}: não existe (a capacidade K é menor que c).`);
    } else if (unstable.length > 0) {
      out.push(`c = ${s.servers}: instável a partir de λ = ${formatNumber(unstable[0].value)} req/s.`);
    }
  }
  return out;
}

// ---------- sensibilidade ----------

export interface TornadoRow {
  name: SweepVariable;
  label: string;
  low: number | null;     // variação % da métrica quando o parâmetro diminui
  high: number | null;
  elasticity: number | null;
}

export function tornadoRows(parameters: ParameterSensitivity[], metric: MetricName): TornadoRow[] {
  const rows = parameters.map((p) => {
    const effect = p.effects[metric];
    return {
      name: p.name,
      label: VARIABLE_INFO[p.name].label,
      low: effect?.low_change_pct ?? null,
      high: effect?.high_change_pct ?? null,
      elasticity: effect?.elasticity ?? null,
    };
  });
  const size = (r: TornadoRow) => Math.max(Math.abs(r.low ?? 0), Math.abs(r.high ?? 0));
  return rows.sort((a, b) => size(b) - size(a));
}

export function tornadoChart(rows: TornadoRow[], metric: MetricName, colors: ThemeColors) {
  const labels = rows.map((r) => r.label);
  const bar = (name: string, key: "low" | "high", color: string, pattern: string) => {
    const kept = rows.filter((r) => r[key] !== null);
    return {
      type: "bar", orientation: "h", name,
      x: kept.map((r) => r[key]), y: kept.map((r) => r.label),
      text: kept.map((r) => formatSignedPercent(r[key] as number, 1)), textposition: "outside", cliponaxis: false,
      marker: { color: color, pattern: { shape: pattern }, line: { color, width: 1 } },
      hovertemplate: "%{y}: %{x:+.2f}%<extra>" + name + "</extra>",
    };
  };
  return {
    data: [
      bar("Parâmetro diminui", "low", colors.accent, ""),
      bar("Parâmetro aumenta", "high", colors.danger, "/"),
    ],
    layout: {
      ...BASE_LAYOUT(colors),
      height: 140 + 70 * rows.length,
      barmode: "overlay",
      xaxis: {
        title: { text: `Variação de ${METRIC_INFO[metric].short} (%)` }, ticksuffix: "%", zeroline: true,
        zerolinecolor: colors.textMuted, zerolinewidth: 1.5, gridcolor: colors.border, fixedrange: true,
      },
      yaxis: { automargin: true, autorange: "reversed", categoryorder: "array", categoryarray: labels, fixedrange: true },
    },
  };
}
