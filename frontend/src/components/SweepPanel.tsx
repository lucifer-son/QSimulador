import { IconAlertTriangle, IconInfoCircle } from "@tabler/icons-react";
import { useEffect, useMemo, useRef, useState, type FormEvent } from "react";
import { runSweep, type SweepResponse } from "../api/experiments";
import { describeUnstable, sweepChart, sweepSeries, type XAxis } from "../charts/experiments";
import {
  buildSweepBody, experimentFieldErrors, suggestRange, sweepVariables, VARIABLE_INFO,
  type ExpErrors, type RangeText, type SimText, type SweepVariable, type SystemText,
} from "../domain/experiments";
import { formatInteger, formatNumber } from "../domain/format";
import type { MetricName, ModelKey } from "../domain/types";
import { useExperiment } from "../hooks/useExperiment";
import { useThemeColors } from "../hooks/useThemeColors";
import { experimentRecord, experimentTitle } from "../domain/records";
import { FixedParameters, MetricSelect, ResultArea, RunButtons } from "./ExperimentParts";
import { metricTitle } from "./MetricsTable";
import { PlotlyChart } from "./PlotlyChart";
import { SaveButton } from "./SaveButton";
import { SweepTable } from "./SweepTable";
import { TextField } from "./TextField";

interface Props {
  active: boolean;
  model: ModelKey;
  system: SystemText;
  sim: SimText;
}

export function SweepPanel({ active, model, system, sim }: Props) {
  const variables = sweepVariables(model);
  const [chosen, setChosen] = useState<SweepVariable>("lambda");
  const variable = variables.includes(chosen) ? chosen : "lambda";   // trocar de modelo pode tirar c ou K
  const [range, setRange] = useState<RangeText>(() => suggestRange("lambda", model, system));
  const [simulate, setSimulate] = useState(false);
  const [simText, setSimText] = useState<SimText>(sim);
  const [errors, setErrors] = useState<ExpErrors>({});
  const { state, run, cancel } = useExperiment<SweepResponse>();
  const lastRequest = useRef<unknown>(null);   // o pedido que gerou o resultado, para o histórico

  // Ao trocar a variável (ou o modelo), a faixa antiga deixa de fazer sentido: sugere outra.
  useEffect(() => {
    setRange(suggestRange(variable, model, system));
    setErrors({});
    // O Laboratório pode mudar depois; a faixa só é refeita a pedido (botão "Sugerir faixa").
  }, [variable, model]);

  useEffect(() => {
    if (state.status === "error") setErrors(experimentFieldErrors(state.error.fields, state.error.code));
  }, [state]);

  const submit = (e: FormEvent) => {
    e.preventDefault();
    const built = buildSweepBody(model, variable, system, range, { ...simText, enabled: simulate });
    if (!built.ok) {
      setErrors(built.errors);
      return;
    }
    setErrors({});
    lastRequest.current = built.body;
    void run((signal) => runSweep(built.body, signal));
  };

  const edit = (field: keyof RangeText) => (value: string) => {
    setRange((r) => ({ ...r, [field]: value }));
    setErrors(({ [field]: _gone, ...rest }) => rest);
  };
  const editSim = (field: keyof SimText) => (value: string) => {
    setSimText((s) => ({ ...s, [field]: value }));
    setErrors(({ [field]: _gone, ...rest }) => rest);
  };
  const { unit, label } = VARIABLE_INFO[variable];
  const unitHint = unit ? `Em ${unit}` : "Inteiro";

  return (
    <div className="exp-grid" hidden={!active} role="tabpanel" id="exp-panel-sweep" aria-labelledby="exp-tab-sweep">
      <form className="panel params" aria-label="Parâmetros da varredura" onSubmit={submit}>
        <p className="sub">
          Varia um parâmetro em uma faixa e mostra como as métricas respondem, inclusive onde o sistema satura.
        </p>
        <FixedParameters model={model} system={system} skip={variable} />

        <h2 className="group-title">Varredura</h2>
        <div className="field">
          <label htmlFor="sweep-variable">Parâmetro varrido</label>
          <select id="sweep-variable" value={variable} onChange={(e) => setChosen(e.target.value as SweepVariable)}>
            {variables.map((v) => <option key={v} value={v}>{VARIABLE_INFO[v].label}</option>)}
          </select>
        </div>
        <div className="grid2 spaced">
          <TextField id="sweep-start" label="Início" value={range.start} error={errors.start} hint={unitHint} onChange={edit("start")} />
          <TextField id="sweep-end" label="Fim" value={range.end} error={errors.end} onChange={edit("end")} />
          <TextField id="sweep-step" label="Passo" value={range.step} error={errors.step} onChange={edit("step")} />
          <button
            type="button" className="btn btn-small suggest"
            onClick={() => { setRange(suggestRange(variable, model, system)); setErrors({}); }}
          >
            Sugerir faixa
          </button>
        </div>

        <label className="check">
          <input type="checkbox" checked={simulate} onChange={(e) => setSimulate(e.target.checked)} />
          Simular também cada ponto
        </label>
        {simulate && (
          <>
            <div className="grid2 spaced">
              <TextField id="sweep-time" label="Tempo por ponto (s)" value={simText.simulationTime} error={errors.simulationTime} onChange={editSim("simulationTime")} />
              <TextField id="sweep-reps" label="Réplicas por ponto" value={simText.replications} error={errors.replications} hint="De 2 a 100" onChange={editSim("replications")} />
              <TextField id="sweep-warmup" label="Warm-up (s)" value={simText.warmupTime} error={errors.warmupTime} onChange={editSim("warmupTime")} />
              <TextField id="sweep-seed" label="Semente" value={simText.seed} error={errors.seed} hint="Vazio = aleatória" onChange={editSim("seed")} />
            </div>
            <p className="note">
              Só os pontos estáveis são simulados, todos com a mesma semente. O total de chegadas esperadas
              somando os pontos tem limite de 5.000.000.
            </p>
          </>
        )}

        <div className="actions spaced">
          <RunButtons busy={state.status === "loading"} label="Gerar curva" onCancel={cancel} />
        </div>
      </form>

      <ResultArea
        state={state}
        idleTitle="Varra um parâmetro"
        idleText={`Escolha a faixa de ${label} e clique em Gerar curva para ver as métricas e onde o sistema satura.`}
        loadingText={simulate ? "Calculando e simulando a faixa" : "Calculando a faixa"}
      >
        {(result) => {
          const title = experimentTitle("sweep", result.model as ModelKey, result);
          return (
            <>
              <SaveButton
                suggestedTitle={title}
                build={(t) => experimentRecord("sweep", result.model as ModelKey, lastRequest.current, result, t ?? title)}
              />
              <SweepResult result={result} />
            </>
          );
        }}
      </ResultArea>
    </div>
  );
}

export function SweepResult({ result }: { result: SweepResponse }) {
  const colors = useThemeColors();
  const model = result.model as ModelKey;
  const variable = result.variable as SweepVariable;
  const [metric, setMetric] = useState<MetricName>("W");
  const [xAxis, setXAxis] = useState<XAxis>("value");

  const hasMetric = (n: MetricName) => result.points.some((p) => p.metrics && n in p.metrics);
  const shown = hasMetric(metric) ? metric : "rho";
  const series = useMemo(() => sweepSeries(result.points, shown, xAxis), [result, shown, xAxis]);
  const chart = useMemo(
    () => sweepChart(series, shown, variable, xAxis, colors),
    [series, shown, variable, xAxis, colors],
  );
  const unstable = describeUnstable(result.points, variable);
  const sim = result.simulation;
  const skipped = sim ? result.points.filter((p) => p.status === "ok" && !p.simulation).length : 0;

  return (
    <>
      {unstable && (
        <div className="banner banner-warning" role="status">
          <IconAlertTriangle size={18} aria-hidden="true" />
          <div>{unstable}</div>
        </div>
      )}
      {sim && (
        <div className="banner banner-info" role="status">
          <IconInfoCircle size={18} aria-hidden="true" />
          <div>
            Simulação: {formatInteger(sim.replications)} réplicas de {formatNumber(sim.simulation_time)} s por
            ponto, semente {sim.seed} (a mesma em todos os pontos).
            {skipped > 0 && <div className="banner-detail">{skipped} ponto(s) sem simulação: tempo curto demais.</div>}
          </div>
        </div>
      )}

      <div className="exp-controls">
        <MetricSelect id="sweep-metric" model={model} value={shown} available={hasMetric} onChange={setMetric} />
        <div className="field inline">
          <label htmlFor="sweep-xaxis">Eixo horizontal</label>
          <select id="sweep-xaxis" value={xAxis} onChange={(e) => setXAxis(e.target.value as XAxis)}>
            <option value="value">{VARIABLE_INFO[variable].label}</option>
            <option value="utilization">Carga oferecida λ/(c·μ)</option>
          </select>
        </div>
      </div>

      {series.x.length > 0 ? (
        <section className="block">
          <p className="sub">
            Curva analítica{sim ? " e média simulada com intervalo de confiança" : ""}. A faixa sombreada é o trecho
            instável; os quadrados marcam alta utilização (λ/cμ ≥ 80%).
          </p>
          <PlotlyChart
            data={chart.data} layout={chart.layout}
            label={`${metricTitle(shown)} em função de ${VARIABLE_INFO[variable].label}`}
          />
        </section>
      ) : (
        <p className="empty-note">Nenhum ponto da faixa pôde ser calculado, então não há curva para mostrar.</p>
      )}
      <SweepTable result={result} />
    </>
  );
}
