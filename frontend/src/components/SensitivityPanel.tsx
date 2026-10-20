import { IconInfoCircle, IconX } from "@tabler/icons-react";
import { useEffect, useMemo, useRef, useState, type FormEvent } from "react";
import { runSensitivity, type SensitivityResponse } from "../api/experiments";
import { tornadoChart, tornadoRows } from "../charts/experiments";
import {
  buildSensitivityBody, experimentFieldErrors, VARIABLE_INFO, type ExpErrors, type SweepVariable, type SystemText,
} from "../domain/experiments";
import { formatMetric, formatNumber, formatSignedPercent } from "../domain/format";
import type { ExperimentModelKey, MetricName } from "../domain/types";
import { useExperiment } from "../hooks/useExperiment";
import { useThemeColors } from "../hooks/useThemeColors";
import { experimentRecord, experimentTitle } from "../domain/records";
import { FixedParameters, MetricSelect, ResultArea, RunButtons } from "./ExperimentParts";
import { metricTitle } from "./MetricsTable";
import { PlotlyChart } from "./PlotlyChart";
import { SaveButton } from "./SaveButton";
import { TextField } from "./TextField";

interface Props {
  active: boolean;
  model: ExperimentModelKey;
  system: SystemText;
}

export function SensitivityPanel({ active, model, system }: Props) {
  const [delta, setDelta] = useState("10");
  const [errors, setErrors] = useState<ExpErrors>({});
  const { state, run, cancel } = useExperiment<SensitivityResponse>();
  const lastRequest = useRef<unknown>(null);   // o pedido que gerou o resultado, para o histórico

  useEffect(() => {
    if (state.status === "error") setErrors(experimentFieldErrors(state.error.fields, state.error.code));
  }, [state]);

  const submit = (e: FormEvent) => {
    e.preventDefault();
    const built = buildSensitivityBody(model, system, delta);
    if (!built.ok) {
      setErrors(built.errors);
      return;
    }
    setErrors({});
    lastRequest.current = built.body;
    void run((signal) => runSensitivity(built.body, signal));
  };

  return (
    <div className="exp-grid" hidden={!active} role="tabpanel" id="exp-panel-sensitivity" aria-labelledby="exp-tab-sensitivity">
      <form className="panel params" aria-label="Parâmetros da análise de sensibilidade" onSubmit={submit}>
        <p className="sub">
          Perturba um parâmetro por vez em torno do sistema do Laboratório e mede quanto cada métrica muda.
        </p>
        <FixedParameters model={model} system={system} title="Ponto base" />
        <h2 className="group-title">Perturbação</h2>
        <TextField
          id="sens-delta" label={model === "mg1" ? "Variação de λ, μ e CV (%)" : "Variação de λ e μ (%)"} value={delta} error={errors.delta}
          hint={model === "mg1" ? "De 0 a 50. O k do Erlang varia ±1." : "De 0 a 50. c e K variam ±1."}
          onChange={(v) => { setDelta(v); setErrors(({ delta: _gone, ...rest }) => rest); }}
        />
        <div className="actions spaced">
          <RunButtons busy={state.status === "loading"} label="Analisar sensibilidade" onCancel={cancel} />
        </div>
      </form>

      <ResultArea
        state={state}
        idleTitle="Veja o que mais pesa no desempenho"
        idleText="A análise mostra qual parâmetro move mais cada métrica, e como isso piora perto da saturação."
        loadingText="Calculando a sensibilidade"
      >
        {(result) => {
          const title = experimentTitle("sensitivity", model, {});
          return (
            <>
              <SaveButton
                suggestedTitle={title}
                build={(t) => experimentRecord("sensitivity", model, lastRequest.current, result, t ?? title)}
              />
              <SensitivityResult result={result} model={model} />
            </>
          );
        }}
      </ResultArea>
    </div>
  );
}

export function SensitivityResult({ result, model }: { result: SensitivityResponse; model: ExperimentModelKey }) {
  const colors = useThemeColors();
  const [metric, setMetric] = useState<MetricName>("W");
  const shown = metric in result.base_metrics ? metric : "rho";
  const rows = useMemo(() => tornadoRows(result.parameters, shown), [result, shown]);
  const chart = useMemo(() => tornadoChart(rows, shown, colors), [rows, shown, colors]);
  const unitFor = (name: SweepVariable) => (name === "lambda" || name === "mu" ? "req/s" : "");   // cv e k não têm unidade

  const sideCell = (side: SensitivityResponse["parameters"][number]["low"], change: number | null, name: SweepVariable) =>
    side.status === "ok" ? (
      <>
        {formatNumber(side.value)} {unitFor(name)}
        <small className="cell-sim">{change === null ? "—" : formatSignedPercent(change, 1)}</small>
      </>
    ) : (
      <span className="tag tag-bad" title={side.message ?? undefined}>
        <IconX size={14} aria-hidden="true" />{side.status === "unstable" ? "instável" : "inválido"}
      </span>
    );

  return (
    <>
      <div className="banner banner-info" role="status">
        <IconInfoCircle size={18} aria-hidden="true" />
        <div>
          Ponto base: {metricTitle(shown)} = {formatMetric(shown, result.base_metrics[shown], { precise: true })}.
          {model === "mg1"
            ? `λ, μ e o CV variam ±${formatNumber(result.delta_pct)}%; o k do Erlang varia ±1 unidade.`
            : `λ e μ variam ±${formatNumber(result.delta_pct)}%; c e K variam ±1 unidade.`}
          <div className="banner-detail">
            Elasticidade: quantos % a métrica muda para cada 1% de mudança no parâmetro. Quanto maior em módulo, mais sensível.
          </div>
        </div>
      </div>
      <div className="exp-controls">
        <MetricSelect id="sens-metric" model={model} value={shown} onChange={setMetric} />
      </div>
      <section className="block">
        <p className="sub">Variação da métrica em cada lado da perturbação, do parâmetro que mais pesa ao que menos pesa.</p>
        <PlotlyChart data={chart.data} layout={chart.layout} label={`Sensibilidade de ${metricTitle(shown)} aos parâmetros`} />
      </section>
      <div className="table-wrap">
        <table className="table">
          <caption className="sr-only">Sensibilidade de {metricTitle(shown)} a cada parâmetro</caption>
          <thead>
            <tr>
              <th scope="col">Parâmetro</th>
              <th scope="col" className="num">Base</th>
              <th scope="col" className="num">Diminui para</th>
              <th scope="col" className="num">Aumenta para</th>
              <th scope="col" className="num">Elasticidade</th>
            </tr>
          </thead>
          <tbody>
            {result.parameters.map((p) => {
              const effect = p.effects[shown];
              return (
                <tr key={p.name}>
                  <th scope="row">{VARIABLE_INFO[p.name].label}</th>
                  <td className="num">{formatNumber(p.base_value)} {unitFor(p.name)}</td>
                  <td className="num">{sideCell(p.low, effect?.low_change_pct ?? null, p.name)}</td>
                  <td className="num">{sideCell(p.high, effect?.high_change_pct ?? null, p.name)}</td>
                  <td className="num">
                    {effect?.elasticity == null ? "—" : formatNumber(Number(effect.elasticity.toFixed(3)))}
                    {effect?.elasticity != null && Math.abs(effect.elasticity) >= 2 && (
                      <small className="cell-sim">alta sensibilidade</small>
                    )}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </>
  );
}
