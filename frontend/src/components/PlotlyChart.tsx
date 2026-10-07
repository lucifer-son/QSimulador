import { useEffect, useRef } from "react";

interface Props {
  data: object[];
  layout: object;
  label: string;
}

/** Carrega o Plotly só quando o primeiro gráfico aparece (fora do pacote inicial). */
export function PlotlyChart({ data, layout, label }: Props) {
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    let cancelled = false;
    void import("plotly.js-basic-dist-min").then(({ default: Plotly }) => {
      if (!cancelled) {
        void Plotly.react(el, data, { autosize: true, ...layout }, { displayModeBar: false, responsive: true });
      }
    });
    return () => {
      cancelled = true;
    };
  }, [data, layout]);

  useEffect(() => {
    const el = ref.current;
    return () => {
      if (el) void import("plotly.js-basic-dist-min").then(({ default: Plotly }) => Plotly.purge(el));
    };
  }, []);

  return <div ref={ref} role="img" aria-label={label} className="plot" />;
}
