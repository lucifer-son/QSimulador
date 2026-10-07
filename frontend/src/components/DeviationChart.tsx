import { useMemo } from "react";
import { deviationChart, deviationData } from "../charts/deviation";
import { METRIC_INFO } from "../domain/metrics";
import type { ViewResult } from "../domain/types";
import { useThemeColors } from "../hooks/useThemeColors";
import { PlotlyChart } from "./PlotlyChart";

export function DeviationChart({ result }: { result: ViewResult }) {
  const colors = useThemeColors();
  const { points, omitted } = useMemo(() => deviationData(result.metrics), [result.metrics]);
  const chart = useMemo(() => deviationChart(points, colors), [points, colors]);
  if (points.length === 0) return null;

  const level = Math.round((result.confidenceLevel ?? 0.95) * 100);
  return (
    <section className="block" aria-labelledby="deviation-title">
      <h3 id="deviation-title">Simulação em relação ao analítico</h3>
      <p className="sub">Diferença em %, barras = IC de {level}%. Se a barra cruza o zero, o analítico está dentro do IC.</p>
      <PlotlyChart
        data={chart.data}
        layout={chart.layout}
        label="Diferença percentual da simulação em relação ao analítico, com intervalo de confiança, por métrica"
      />
      {omitted.length > 0 && (
        <p className="note">
          Fora do gráfico (valor analítico igual a 0): {omitted.map((n) => METRIC_INFO[n].short).join(", ")}.
        </p>
      )}
    </section>
  );
}
