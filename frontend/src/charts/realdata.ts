import type { AnalysisResponse, LevelComparison } from "../api/realdata";
import type { ThemeColors } from "../hooks/useThemeColors";

export type LevelMetric = "W" | "throughput";

const TITLE: Record<LevelMetric, string> = {
  W: "Tempo médio de resposta (s)",
  throughput: "Vazão (req/s)",
};

/** Medido × modelo por nível de carga (usuários). Medido com IC por lotes; modelo tracejado. */
export function levelChart(
  result: AnalysisResponse, comparison: LevelComparison[], metric: LevelMetric, colors: ThemeColors,
) {
  const hasUsers = result.levels.every((l) => l.users !== null);
  const x = result.levels.map((l, i) => (hasUsers ? (l.users as number) : i + 1));
  const summaryKey = metric === "W" ? "W" : "throughput";
  const observed = result.levels.map((l) => (metric === "W" ? l.metrics.mean_response : l.metrics.throughput));
  const above = result.levels.map((l, i) => Math.max((l.metrics.summaries[summaryKey]?.ci_high ?? observed[i]) - observed[i], 0));
  const below = result.levels.map((l, i) => Math.max(observed[i] - (l.metrics.summaries[summaryKey]?.ci_low ?? observed[i]), 0));

  const data: object[] = [{
    x, y: observed, name: "Medido (IC 95%)", mode: "lines+markers",
    line: { color: colors.accent, width: 2 }, marker: { symbol: "circle", size: 8, color: colors.accent },
    error_y: { type: "data", symmetric: false, array: above, arrayminus: below, color: colors.accent },
  }];
  if (comparison.length === result.levels.length && comparison.length > 0) {
    data.push({
      x, y: comparison.map((c) => c.metrics[metric]?.model ?? null), name: "Modelo", mode: "lines+markers",
      line: { color: colors.textSecondary, width: 2, dash: "dash" }, marker: { symbol: "diamond", size: 8, color: colors.textSecondary },
    });
  }
  const layout = {
    height: 340,
    margin: { l: 70, r: 20, t: 10, b: 90 },
    separators: ",.",
    paper_bgcolor: "rgba(0,0,0,0)", plot_bgcolor: "rgba(0,0,0,0)",
    font: { color: colors.textSecondary, size: 12 }, dragmode: false,
    legend: { orientation: "h", y: -0.4 },
    xaxis: { title: { text: hasUsers ? "Usuários simultâneos" : "Janela de análise" }, gridcolor: colors.border, dtick: hasUsers ? undefined : 1 },
    yaxis: { title: { text: TITLE[metric] }, gridcolor: colors.border, rangemode: "tozero" },
  };
  return { data, layout };
}
