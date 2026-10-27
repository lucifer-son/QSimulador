import { useMemo, useState } from "react";
import type { FitCandidate, FitResult } from "../api/analysis";
import { fitChart } from "../charts/analysis";
import { formatP } from "../domain/analysis";
import { useThemeColors } from "../hooks/useThemeColors";
import { PlotlyChart } from "./PlotlyChart";

const num = (x: number, digits = 4): string => x.toLocaleString("pt-BR", { maximumSignificantDigits: digits });

const PARAM_LABELS: Record<string, string> = {
  mean: "média", rate: "taxa", k: "k", mu: "μ", sigma: "σ", shape: "forma", scale: "escala", min: "mín", max: "máx", cv: "CV",
};
const SHOWN = ["k", "rate", "mu", "sigma", "shape", "scale", "min", "max", "mean"];

function parameters(c: FitCandidate): string {
  const keys = SHOWN.filter((key) => key in c.parameters && !(c.key === "lognormal" && key === "mean"));
  return keys.map((key) => `${PARAM_LABELS[key]} = ${num(c.parameters[key])}`).join(", ");
}

function adequacy(c: FitCandidate): string {
  if (c.adequate === null) return "—";
  return c.adequate ? "adequada" : "rejeitada";
}

/** Resultado do ajuste: resumo, sugestão de modelo, histograma com as curvas e tabela de candidatas. */
export function FitResultView({ result }: { result: FitResult }) {
  const colors = useThemeColors();
  const [visible, setVisible] = useState<string[]>(() => (result.best ? [result.best] : result.candidates.slice(0, 1).map((c) => c.key)));
  const chart = useMemo(() => fitChart(result, colors, visible), [result, colors, visible]);
  const toggle = (key: string) => setVisible((v) => (v.includes(key) ? v.filter((k) => k !== key) : [...v, key]));
  const [lo, hi] = result.cv_ci ?? [null, null];
  const hasP = result.bootstrap > 0;

  return (
    <div className="fit-result">
      <section className="block">
        <h3>Resumo da amostra</h3>
        <p>
          n = {result.n.toLocaleString("pt-BR")} · média {num(result.mean)} · desvio {num(result.std)} ·
          {" "}<strong>CV = {num(result.cv, 3)}</strong>
          {lo !== null && hi !== null && <> (IC 95 %: {num(lo, 3)} a {num(hi, 3)})</>} · de {num(result.minimum)} a {num(result.maximum)}
        </p>
        <div className="callout" role="note">
          <strong>Modelo sugerido: {result.suggestion.model ?? "fora do catálogo"}.</strong> {result.suggestion.text}
        </div>
      </section>

      {result.warnings.map((w) => <p key={w} className="note" role="note">{w}</p>)}
      {result.none_adequate && (
        <p className="callout state-error" role="alert">
          <strong>Nenhuma candidata é adequada.</strong> Todas têm p-valor abaixo de α = {num(result.alpha, 2)}: a amostra não segue
          nenhuma destas distribuições. Use o AIC só para comparar, não como prova de que alguma serve.
        </p>
      )}

      {!result.degenerate && (
        <>
          <section className="block">
            <h3>Histograma e curvas ajustadas</h3>
            <PlotlyChart data={chart.data} layout={chart.layout} label="Histograma da amostra com a densidade das distribuições ajustadas" />
            <div className="field inline fit-curves" role="group" aria-label="Curvas mostradas">
              {result.candidates.map((c) => (
                <label key={c.key}>
                  <input type="checkbox" checked={visible.includes(c.key)} onChange={() => toggle(c.key)} /> {c.label}
                </label>
              ))}
            </div>
          </section>

          <section className="block">
            <h3>Candidatas</h3>
            <div className="table-wrap">
              <table className="table">
                <thead>
                  <tr>
                    <th scope="col">Distribuição</th><th scope="col">Parâmetros</th><th scope="col">CV</th>
                    <th scope="col">AIC</th><th scope="col">ΔAIC</th>
                    <th scope="col">p-valor{hasP ? ` (B = ${result.bootstrap})` : ""}</th><th scope="col">Aderência</th>
                  </tr>
                </thead>
                <tbody>
                  {result.candidates.map((c) => (
                    <tr key={c.key} className={c.key === result.best ? "row-best" : undefined}>
                      <th scope="row">{c.label}{c.key === result.best && " ★"}</th>
                      <td>{parameters(c)}</td>
                      <td>{num(c.cv, 3)}</td>
                      <td>{num(c.aic, 6)}{!c.comparable_aic && <sup title="AIC não comparável: o suporte depende da amostra"> ¹</sup>}</td>
                      <td>{c.delta_aic === null ? "—" : num(c.delta_aic, 3)}</td>
                      <td>{c.p_value === null ? "—" : `${formatP(c.p_value)} ± ${num(c.p_value_se ?? 0, 2)}`}</td>
                      <td>{adequacy(c)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            <p className="sub">
              ★ menor AIC entre as comparáveis. ¹ O AIC da uniforme não é diretamente comparável com o das outras: o suporte [mín, máx]
              depende da amostra, então ela não entra na escolha do melhor AIC. O p-valor é de aderência por Monte Carlo
              (bootstrap paramétrico, parâmetros reestimados em cada réplica); o “±” é o erro de Monte Carlo.
            </p>
          </section>
        </>
      )}

      {result.service_suggestion && (
        <p className="sub">
          Serviço sugerido para o Laboratório: <code>{JSON.stringify(result.service_suggestion)}</code> (semente {result.seed}).
        </p>
      )}
    </div>
  );
}
