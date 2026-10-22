import type { SizingRow } from "../api/sizing";
import type { ThemeColors } from "../hooks/useThemeColors";
import { withAlpha } from "./replications";

const BASE_LAYOUT = (colors: ThemeColors) => ({
  height: 340,
  margin: { l: 70, r: 20, t: 10, b: 90 },
  separators: ",.",
  paper_bgcolor: "rgba(0,0,0,0)",
  plot_bgcolor: "rgba(0,0,0,0)",
  font: { color: colors.textSecondary, size: 12 },
  dragmode: false,
  legend: { orientation: "h", y: -0.3 },
});

const okRows = (rows: SizingRow[]) => rows.filter((r) => r.status === "ok");

/** Nível de serviço (%) por número de servidores, com a linha da meta. */
export function levelChart(rows: SizingRow[], targetPct: number | null, colors: ThemeColors) {
  const ok = okRows(rows).filter((r) => r.service_level !== null);
  const x = ok.map((r) => r.servers);
  const data: object[] = [{
    type: "scatter", mode: "lines+markers", name: "Nível de serviço", x, y: ok.map((r) => r.service_level! * 100),
    line: { color: colors.accent, width: 2 }, marker: { color: colors.accent, size: 7 },
    hovertemplate: "c = %{x}: %{y:.1f}%<extra></extra>",
  }];
  const shapes = targetPct === null ? [] : [{
    type: "line", xref: "paper", x0: 0, x1: 1, yref: "y", y0: targetPct, y1: targetPct,
    line: { color: colors.danger, width: 1.5, dash: "dash" },
  }];
  const annotations = targetPct === null ? [] : [{
    xref: "paper", x: 1, xanchor: "right", yref: "y", y: targetPct, yanchor: "bottom", showarrow: false,
    text: `meta ${targetPct.toLocaleString("pt-BR", { maximumFractionDigits: 1 })}%`, font: { color: colors.danger, size: 11 },
  }];
  const layout = {
    ...BASE_LAYOUT(colors), shapes, annotations,
    xaxis: { title: { text: "Servidores c" }, dtick: 1, gridcolor: colors.border, fixedrange: true },
    yaxis: { title: { text: "P(Wq ≤ t)" }, ticksuffix: "%", range: [0, 102], gridcolor: colors.border, fixedrange: true },
  };
  return { data, layout };
}

/** Custo total por número de servidores, com a decomposição e o ótimo destacado. `factor` converte para a unidade escolhida. */
export function costChart(
  rows: SizingRow[], optimal: number, factor: number, unitLabel: string, colors: ThemeColors,
) {
  const ok = okRows(rows).filter((r) => r.cost !== null);
  const x = ok.map((r) => r.servers);
  const scaled = (pick: (r: SizingRow) => number | null) => ok.map((r) => (pick(r) ?? 0) * factor);
  const best = ok.find((r) => r.servers === optimal);
  const data: object[] = [
    {
      type: "scatter", mode: "lines+markers", name: "Custo total", x, y: scaled((r) => r.cost),
      line: { color: colors.accent, width: 2.5 }, marker: { color: colors.accent, size: 7 },
      hovertemplate: "c = %{x}: %{y:,.2f}<extra>Total</extra>",
    },
    {
      type: "scatter", mode: "lines", name: "Servidores", x, y: scaled((r) => r.server_cost),
      line: { color: colors.textMuted, width: 1.5, dash: "dot" }, hovertemplate: "c = %{x}: %{y:,.2f}<extra>Servidores</extra>",
    },
    {
      type: "scatter", mode: "lines", name: "Espera", x, y: scaled((r) => r.wait_cost),
      line: { color: colors.danger, width: 1.5, dash: "dash" }, hovertemplate: "c = %{x}: %{y:,.2f}<extra>Espera</extra>",
    },
  ];
  if (ok.some((r) => (r.loss_cost ?? 0) > 0)) {
    data.push({
      type: "scatter", mode: "lines", name: "Perda", x, y: scaled((r) => r.loss_cost),
      line: { color: withAlpha(colors.danger, 0.6), width: 1.5, dash: "dashdot" },
      hovertemplate: "c = %{x}: %{y:,.2f}<extra>Perda</extra>",
    });
  }
  if (best) {
    data.push({
      type: "scatter", mode: "markers", name: `Ótimo (c = ${optimal})`, x: [best.servers], y: [best.cost! * factor],
      marker: { color: "rgba(0,0,0,0)", size: 16, symbol: "circle-open", line: { color: colors.text, width: 2.5 } },
      hoverinfo: "skip",
    });
  }
  const layout = {
    ...BASE_LAYOUT(colors),
    xaxis: { title: { text: "Servidores c" }, dtick: 1, gridcolor: colors.border, fixedrange: true },
    yaxis: { title: { text: `Custo (${unitLabel})` }, automargin: true, gridcolor: colors.border, fixedrange: true, rangemode: "tozero" },
  };
  return { data, layout };
}
