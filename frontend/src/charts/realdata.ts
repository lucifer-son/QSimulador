import type { AnalysisResponse } from "../api/realdata";
import type { SimulatedLevelComparison } from "../api/realdataExtra";
import type { ThemeColors } from "../hooks/useThemeColors";

export type LevelMetric = "W" | "throughput";

const TITLE: Record<LevelMetric, string> = {
  W: "Tempo médio de resposta (s)",
  throughput: "Vazão (req/s)",
};

/** Medido × modelo por nível de carga (usuários). Medido com IC por lotes; modelo tracejado. */
export function levelChart(
  result: Pick<AnalysisResponse, "levels">, comparison: SimulatedLevelComparison[], metric: LevelMetric, colors: ThemeColors,
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
  const simulated = comparison.map((c) => c.metrics[metric]?.simulated_mean ?? null);
  if (comparison.length === result.levels.length && comparison.length > 0 && simulated.every((v) => v !== null)) {
    data.push({
      x, y: simulated, name: "Simulação", mode: "lines+markers",
      line: { color: colors.danger, width: 2, dash: "dot" }, marker: { symbol: "square", size: 7, color: colors.danger },
      error_y: {
        type: "data", symmetric: false, color: colors.danger,
        array: comparison.map((c) => Math.max((c.metrics[metric]?.simulated_ci_high ?? c.metrics[metric]?.simulated_mean ?? 0) - (c.metrics[metric]?.simulated_mean ?? 0), 0)),
        arrayminus: comparison.map((c) => Math.max((c.metrics[metric]?.simulated_mean ?? 0) - (c.metrics[metric]?.simulated_ci_low ?? c.metrics[metric]?.simulated_mean ?? 0), 0)),
      },
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
