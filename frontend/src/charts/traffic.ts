import type {
  ApproachKey, CompareResult, PlanRow, QueueSeries, SweepResult, ValidationApproach,
} from "../api/traffic";
import type { ThemeColors } from "../hooks/useThemeColors";

/** Gráficos do cruzamento semaforizado (Fase 13.1): funções puras que devolvem { data, layout } para o Plotly. */

export interface Chart { data: object[]; layout: object }

const A1_FALLBACK = "#378ADD";

/** Cor de cada aproximação: o destaque do tema e uma segunda cor distinta (sem depender só de cor: formas e nomes). */
export const approachColor = (colors: ThemeColors, key: ApproachKey): string => (key === "a1" ? colors.accent || A1_FALLBACK : "#D85A30");

function baseLayout(colors: ThemeColors, xTitle: string, yTitle: string, extra: object = {}): object {
  const axis = (title: string) => ({
    title: { text: title, font: { size: 12, color: colors.textSecondary } },
    color: colors.textSecondary, gridcolor: colors.border, zerolinecolor: colors.border, tickfont: { size: 11 },
  });
  return {
    height: 340, margin: { l: 56, r: 16, t: 16, b: 52 },
    paper_bgcolor: "rgba(0,0,0,0)", plot_bgcolor: "rgba(0,0,0,0)",
    font: { color: colors.text, family: "inherit" },
    xaxis: axis(xTitle), yaxis: { ...axis(yTitle), rangemode: "tozero" },
    legend: { orientation: "h", y: -0.25, font: { size: 11 } },
    hovermode: "x unified",
    ...extra,
  };
}

const rgba = (hex: string, alpha: number): string => {
  const m = /^#([0-9a-f]{6})$/i.exec(hex);
  if (!m) return hex;
  const n = parseInt(m[1], 16);
  return `rgba(${n >> 16},${(n >> 8) & 255},${n & 255},${alpha})`;
};

/** Fila de cada aproximação ao longo do tempo: média das réplicas e IC da média. */
export function queueSeriesChart(series: QueueSeries, names: Record<ApproachKey, string>, colors: ThemeColors): Chart {
  const minutes = series.times.map((t) => t / 60);
  const data: object[] = [];
  for (const key of ["a1", "a2"] as ApproachKey[]) {
    const color = approachColor(colors, key);
    const band = series[key];
    data.push(
      { x: minutes, y: band.ci_high, type: "scatter", mode: "lines", line: { width: 0 }, hoverinfo: "skip", showlegend: false },
      { x: minutes, y: band.ci_low, type: "scatter", mode: "lines", line: { width: 0 }, fill: "tonexty", fillcolor: rgba(color, 0.18), hoverinfo: "skip", showlegend: false },
      { x: minutes, y: band.mean, type: "scatter", mode: "lines", name: names[key], line: { color, width: 2, dash: key === "a1" ? "solid" : "dash" } },
    );
  }
  return { data, layout: baseLayout(colors, "Tempo (min)", "Fila (veículos)") };
}

/** Atraso médio do cruzamento por plano, com o IC. */
export function planDelayChart(result: CompareResult, colors: ThemeColors): Chart {
  const rows: PlanRow[] = [result.base, ...result.plans].filter((r) => r.status === "ok");
  const metric = (r: PlanRow) => (r.metrics as Record<string, Record<string, { simulation: { mean: number; ci_low?: number | null; ci_high?: number | null } | null }>>).x?.delay_censored?.simulation;
  const names = rows.map((r) => r.name);
  const mean = rows.map((r) => metric(r)?.mean ?? null);
  const plus = rows.map((r) => { const m = metric(r); return m && m.ci_high != null ? m.ci_high - m.mean : 0; });
  const minus = rows.map((r) => { const m = metric(r); return m && m.ci_low != null ? m.mean - m.ci_low : 0; });
  return {
    data: [{
      x: names, y: mean, type: "bar", name: "Atraso médio (com pendentes)",
      marker: { color: rows.map((r) => (r.role === "base" ? colors.textMuted : colors.accent || A1_FALLBACK)) },
      error_y: { type: "data", symmetric: false, array: plus, arrayminus: minus, color: colors.textSecondary, thickness: 1.5, width: 4 },
    }],
    layout: baseLayout(colors, "Plano", "Atraso médio (s)", { showlegend: false, hovermode: "closest" }),
  };
}

/** Curva do atraso pela divisão do verde (ciclo fixo), com IC, a referência de Webster e o ponto de menor atraso. */
export function sweepChart(result: SweepResult, colors: ThemeColors): Chart {
  const pts = result.points;
  const x = pts.map((p) => p.green[0]);
  const mean = pts.map((p) => p.intersection.delay_censored?.mean ?? null);
  const hi = pts.map((p) => { const d = p.intersection.delay_censored; return d?.ci_high != null ? d.ci_high - d.mean : 0; });
  const lo = pts.map((p) => { const d = p.intersection.delay_censored; return d?.ci_low != null ? d.mean - d.ci_low : 0; });
  const best = pts[result.best_index];
  const accent = colors.accent || A1_FALLBACK;
  return {
    data: [
      { x, y: mean, type: "scatter", mode: "lines+markers", name: "Simulação (IC)", line: { color: accent, width: 2 }, marker: { size: 6 },
        error_y: { type: "data", symmetric: false, array: hi, arrayminus: lo, color: colors.textSecondary, thickness: 1.2, width: 3 } },
      { x, y: pts.map((p) => p.reference_delay), type: "scatter", mode: "lines", name: "Referência analítica (aprox.)", line: { color: colors.textMuted, width: 1.5, dash: "dot" } },
      { x: [best.green[0]], y: [best.intersection.delay_censored?.mean ?? null], type: "scatter", mode: "markers", name: "Menor atraso",
        marker: { symbol: "diamond", size: 13, color: colors.danger, line: { color: colors.text, width: 1 } } },
    ],
    layout: baseLayout(colors, "Verde da fase 1 (s) — o da fase 2 é o resto do ciclo", "Atraso médio do cruzamento (s)", { hovermode: "closest" }),
  };
}

/** Fila observada (pontos) contra a faixa simulada, por intervalo. */
export function validationQueueChart(a: ValidationApproach, name: string, color: string, colors: ThemeColors): Chart {
  const iv = a.intervals;
  const x = iv.map((i) => i.end / 60);
  return {
    data: [
      { x, y: iv.map((i) => i.queue.high), type: "scatter", mode: "lines", line: { width: 0 }, hoverinfo: "skip", showlegend: false },
      { x, y: iv.map((i) => i.queue.low), type: "scatter", mode: "lines", line: { width: 0 }, fill: "tonexty", fillcolor: rgba(color, 0.2), name: "Faixa simulada", hoverinfo: "skip" },
      { x, y: iv.map((i) => i.queue.mean), type: "scatter", mode: "lines", name: "Simulado (média)", line: { color, width: 2 } },
      { x, y: iv.map((i) => i.queue.observed), type: "scatter", mode: "markers", name: "Observado",
        marker: { color: colors.text, size: 6, symbol: "circle-open", line: { width: 1.5, color: colors.text } } },
    ],
    layout: baseLayout(colors, `Tempo (min) — ${name}`, "Fila no fim do intervalo (veículos)"),
  };
}

/** Saídas por intervalo: observado contra a faixa simulada. */
export function validationDeparturesChart(a: ValidationApproach, name: string, color: string, colors: ThemeColors): Chart {
  const iv = a.intervals;
  const x = iv.map((i) => i.end / 60);
  return {
    data: [
      { x, y: iv.map((i) => i.departures.high), type: "scatter", mode: "lines", line: { width: 0 }, hoverinfo: "skip", showlegend: false },
      { x, y: iv.map((i) => i.departures.low), type: "scatter", mode: "lines", line: { width: 0 }, fill: "tonexty", fillcolor: rgba(color, 0.2), name: "Faixa simulada", hoverinfo: "skip" },
      { x, y: iv.map((i) => i.departures.mean), type: "scatter", mode: "lines", name: "Simulado (média)", line: { color, width: 2 } },
      { x, y: iv.map((i) => i.departures.observed), type: "scatter", mode: "markers", name: "Observado",
        marker: { color: colors.text, size: 6, symbol: "circle-open", line: { width: 1.5, color: colors.text } } },
    ],
    layout: baseLayout(colors, `Tempo (min) — ${name}`, "Saídas no intervalo (veículos)"),
  };
}
