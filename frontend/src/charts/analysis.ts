import type { CurvePoint, FitResult, SensitivityCurve, StatesOut, WaitSimulationOut, WaitTailOut } from "../api/analysis";
import type { ThemeColors } from "../hooks/useThemeColors";
import { withAlpha } from "./replications";

const base = (colors: ThemeColors, xTitle: string, yTitle: string, extra: object = {}) => ({
  margin: { l: 64, r: 16, t: 24, b: 52 },
  xaxis: { title: { text: xTitle }, color: colors.textSecondary, gridcolor: colors.border },
  yaxis: { title: { text: yTitle }, color: colors.textSecondary, gridcolor: colors.border },
  paper_bgcolor: "rgba(0,0,0,0)", plot_bgcolor: "rgba(0,0,0,0)",
  font: { color: colors.text }, legend: { orientation: "h", y: -0.25 }, ...extra,
});

/** P(n): barras. A massa fora dos estados mostrados é avisada pela tela, não desenhada. */
export function stateChart(states: StatesOut, colors: ThemeColors) {
  const finite = states.capacity !== null;
  const data = [{
    type: "bar", name: "P(N = n)", x: states.states, y: states.p,
    marker: { color: states.states.map((n) => (finite && n === states.capacity ? colors.danger : colors.accent)) },
    hovertemplate: "n = %{x}<br>P = %{y:.4f}<extra></extra>",
  }];
  return { data, layout: base(colors, "Clientes no sistema (n)", "P(N = n)", { bargap: 0.15, showlegend: false }) };
}

/** P(Wq > t): fórmula fechada (linha) e/ou simulação (média e faixa do IC). */
export function tailChart(
  closed: WaitTailOut | null, sim: WaitSimulationOut | null, colors: ThemeColors, log = false,
) {
  const data: object[] = [];
  if (sim) {
    const ok = sim.survival.every((s) => s.ci_low !== null && s.ci_high !== null);
    if (ok) {
      data.push({
        type: "scatter", mode: "lines", x: [...sim.t, ...[...sim.t].reverse()],
        y: [...sim.survival.map((s) => s.ci_high), ...[...sim.survival].reverse().map((s) => s.ci_low)],
        fill: "toself", fillcolor: withAlpha(colors.accent, 0.2), line: { width: 0 }, hoverinfo: "skip",
        name: "IC da simulação",
      });
    }
    data.push({ type: "scatter", mode: "lines", name: "Simulação", x: sim.t, y: sim.survival.map((s) => s.mean),
      line: { color: colors.accent, width: 2 } });
  }
  if (closed) {
    data.push({ type: "scatter", mode: "lines", name: "Fórmula fechada", x: closed.t, y: closed.survival,
      line: { color: colors.danger, width: 2, dash: sim ? "dash" : "solid" } });
  }
  const layout = base(colors, "Tempo de espera t", "P(Wq > t)", {
    yaxis: { title: { text: "P(Wq > t)" }, color: colors.textSecondary, gridcolor: colors.border,
      type: log ? "log" : "linear", ...(log ? {} : { range: [0, 1] }) },
  });
  return { data, layout };
}

const wqOf = (p: CurvePoint): number | null => (p.status === "ok" ? p.wq : null);

/** Wq × λ: a curva e o ponto do Laboratório marcado; pontos instáveis ficam de fora (a API os sinaliza). */
export function sensitivityChart(curve: SensitivityCurve, colors: ThemeColors, log = false) {
  const ok = curve.points.filter((p) => p.status === "ok" && p.wq !== null);
  const data: object[] = [
    { type: "scatter", mode: "lines", name: "Wq", x: ok.map((p) => p.value), y: ok.map(wqOf), line: { color: colors.accent, width: 2 } },
    { type: "scatter", mode: "markers", name: "Configuração atual", x: [curve.current.value], y: [curve.current.wq],
      marker: { color: colors.danger, size: 11, symbol: "diamond" },
      hovertemplate: "λ = %{x}<br>Wq = %{y:.4g}<extra>atual</extra>" },
  ];
  const layout = base(colors, "Taxa de chegada λ", "Wq", {
    yaxis: { title: { text: "Wq" }, color: colors.textSecondary, gridcolor: colors.border, type: log ? "log" : "linear" },
  });
  return { data, layout };
}

/** Histograma da amostra (densidade) com a curva de cada candidata. */
export function fitChart(result: FitResult, colors: ThemeColors, visible: string[]) {
  const { edges, density } = result.histogram;
  const centers = density.map((_, i) => (edges[i] + edges[i + 1]) / 2);
  const widths = density.map((_, i) => edges[i + 1] - edges[i]);
  const palette: Record<string, string> = {
    exponential: "#d55e00", erlang: "#009e73", lognormal: "#cc79a7", weibull: "#e69f00", uniform: "#56b4e9",
  };
  const data: object[] = [{
    type: "bar", name: "Amostra", x: centers, y: density, width: widths,
    marker: { color: withAlpha(colors.textMuted, 0.45) }, hovertemplate: "densidade %{y:.4g}<extra></extra>",
  }];
  for (const c of result.candidates) {
    if (!visible.includes(c.key)) continue;
    data.push({ type: "scatter", mode: "lines", name: c.label, x: result.curves.t, y: result.curves.pdf[c.key],
      line: { color: palette[c.key] ?? colors.accent, width: 2 } });
  }
  return { data, layout: base(colors, "Valor da amostra", "Densidade", { bargap: 0 }) };
}
