import type { ScenarioRow } from "../api/scenarios";
import { METRIC_INFO } from "../domain/metrics";
import type { MetricName } from "../domain/types";
import type { ThemeColors } from "../hooks/useThemeColors";

/**
 * Diferença de cada cenário contra a base na métrica escolhida, com a barra do IC pareado.
 * Ponto cheio = IC exclui 0 (diferença significativa); vazado = inconclusivo. O losango é a diferença
 * analítica, quando existe: ele deve cair dentro da barra.
 */
export function diffChart(rows: ScenarioRow[], metric: MetricName, colors: ThemeColors, level: number) {
  const items = rows.filter((r) => r.metrics[metric]?.diff);
  const names = items.map((r) => r.name);
  const scale = METRIC_INFO[metric].kind === "fraction" ? 100 : 1;
  const unit = METRIC_INFO[metric].kind === "fraction" ? "p.p." : "";
  const diff = (r: ScenarioRow) => r.metrics[metric]!.diff!;
  const significant = (r: ScenarioRow) => r.metrics[metric]!.verdict !== "inconclusive";

  const data: object[] = [
    {
      type: "scatter", mode: "markers", name: `Diferença simulada (IC ${(level * 100).toLocaleString("pt-BR", { maximumFractionDigits: 2 })}%)`,
      x: items.map((r) => diff(r).mean * scale), y: names, orientation: "h",
      error_x: {
        type: "data", visible: true, color: colors.accent, thickness: 2, width: 6,
        array: items.map((r) => (diff(r).ci_high! - diff(r).mean) * scale),
        arrayminus: items.map((r) => (diff(r).mean - diff(r).ci_low!) * scale),
      },
      marker: {
        size: 10, color: items.map((r) => (significant(r) ? colors.accent : "rgba(0,0,0,0)")),
        line: { color: colors.accent, width: 2 },
      },
      hovertemplate: `%{y}: %{x:,.4g} ${unit}<extra></extra>`,
    },
  ];
  const analytic = items.filter((r) => r.metrics[metric]!.analytic_diff !== null && r.metrics[metric]!.analytic_diff !== undefined);
  if (analytic.length > 0) {
    data.push({
      type: "scatter", mode: "markers", name: "Diferença analítica",
      x: analytic.map((r) => r.metrics[metric]!.analytic_diff! * scale), y: analytic.map((r) => r.name),
      marker: { symbol: "diamond", size: 9, color: colors.danger },
      hovertemplate: `%{y}: %{x:,.4g} ${unit}<extra>analítico</extra>`,
    });
  }
  const layout = {
    height: Math.max(220, 90 + 52 * items.length),
    margin: { l: 150, r: 20, t: 10, b: 80 },
    separators: ",.",
    paper_bgcolor: "rgba(0,0,0,0)", plot_bgcolor: "rgba(0,0,0,0)",
    font: { color: colors.textSecondary, size: 12 }, dragmode: false,
    legend: { orientation: "h", y: -0.35 },
    xaxis: {
      title: { text: `Cenário − base${unit ? ` (${unit})` : ""}` }, zeroline: true, zerolinecolor: colors.text, zerolinewidth: 1.5,
      gridcolor: colors.border, fixedrange: true,
    },
    yaxis: { autorange: "reversed", fixedrange: true },
  };
  return { data, layout };
}
