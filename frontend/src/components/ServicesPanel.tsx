import { IconAlertTriangle } from "@tabler/icons-react";
import { useEffect, useMemo, useRef, useState, type FormEvent } from "react";
import { runServicesComparison, type ServicesComparisonResponse } from "../api/experiments";
import { comparisonChart, describeServiceLimits, metricScale, serviceLabel, serviceLines } from "../charts/experiments";
import {
  buildServicesBody, DEFAULT_SERVICE_CHOICES, experimentFieldErrors, LAB_SERVICE_KEY, MAX_COMPARED_SERVICES,
  serviceMomentsOf, SERVICE_PRESETS, suggestRange, toText,
  type ExpErrors, type RangeText, type SystemText,
} from "../domain/experiments";
import { formatMetric, formatNumber } from "../domain/format";
import { distributionInfo } from "../domain/service";
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
  model: "mg1";
  system: SystemText;
}

/**
 * M/G/1: compara distribuições de serviço com a mesma média E[S] do Laboratório, variando λ.
 * É o experimento que mostra o efeito da variabilidade: quanto maior o CV, mais a fila espera.
 */
export function ServicesPanel({ active, model, system }: Props) {
  const [chosen, setChosen] = useState<string[]>(DEFAULT_SERVICE_CHOICES);
  const [range, setRange] = useState<RangeText>(() => suggestRange("lambda", model, system));
  const [errors, setErrors] = useState<ExpErrors>({});
  const { state, run, cancel } = useExperiment<ServicesComparisonResponse>();
  const lastRequest = useRef<unknown>(null);   // o pedido que gerou o resultado, para o histórico
  const moments = serviceMomentsOf(system);
  const labName = distributionInfo(system.distribution ?? "lognormal").label;

  useEffect(() => {
    if (state.status === "error") setErrors(experimentFieldErrors(state.error.fields, state.error.code));
  }, [state]);

  const toggle = (key: string) => {
    setChosen((current) => (current.includes(key) ? current.filter((k) => k !== key) : [...current, key]));
    setErrors(({ services: _gone, ...rest }) => rest);
  };
  const edit = (field: keyof RangeText) => (value: string) => {
    setRange((r) => ({ ...r, [field]: value }));
    setErrors(({ [field]: _gone, ...rest }) => rest);
  };
  const submit = (e: FormEvent) => {
    e.preventDefault();
    const built = buildServicesBody(system, chosen, range);
    if (!built.ok) {
      setErrors(built.errors);
      return;
    }
    setErrors({});
    lastRequest.current = built.body;
    void run((signal) => runServicesComparison(built.body, signal));
  };

  return (
    <div className="exp-grid" hidden={!active} role="tabpanel" id="exp-panel-services" aria-labelledby="exp-tab-services">
      <form className="panel params" aria-label="Parâmetros da comparação de distribuições" onSubmit={submit}>
        <p className="sub">
          Compara distribuições de serviço com o mesmo tempo médio E[S]{moments ? ` (${toText(moments.mean)} s)` : ""},
          variando λ. Só a variabilidade (o CV) muda entre as curvas.
        </p>
        <FixedParameters model={model} system={system} skip="lambda" />

        <h2 className="group-title">Comparação</h2>
        <fieldset className="field choices">
          <legend>Distribuições a comparar</legend>
          <label className="check">
            <input type="checkbox" checked={chosen.includes(LAB_SERVICE_KEY)} onChange={() => toggle(LAB_SERVICE_KEY)} />
            Serviço do Laboratório ({labName}{moments ? `, CV ${toText(moments.cv)}` : ""})
          </label>
          {SERVICE_PRESETS.map((p) => (
            <label className="check" key={p.key}>
              <input type="checkbox" checked={chosen.includes(p.key)} onChange={() => toggle(p.key)} />
              {p.label}
            </label>
          ))}
          {errors.services
            ? <span className="field-error" role="alert">{errors.services}</span>
            : <span className="field-hint">De 2 a {MAX_COMPARED_SERVICES}.</span>}
        </fieldset>
        {errors.service && <p className="field-error" role="alert">{errors.service}</p>}
        <div className="grid2 spaced">
          <TextField id="services-start" label="λ inicial (req/s)" value={range.start} error={errors.start} onChange={edit("start")} />
          <TextField id="services-end" label="λ final (req/s)" value={range.end} error={errors.end} onChange={edit("end")} />
          <TextField id="services-step" label="Passo de λ" value={range.step} error={errors.step} onChange={edit("step")} />
          <button
            type="button" className="btn btn-small suggest"
            onClick={() => { setRange(suggestRange("lambda", model, system)); setErrors({}); }}
          >
            Sugerir faixa
          </button>
        </div>
        <div className="actions spaced">
          <RunButtons busy={state.status === "loading"} label="Comparar distribuições" onCancel={cancel} />
        </div>
      </form>

      <ResultArea
        state={state}
        idleTitle="Compare distribuições de serviço"
        idleText="Escolha as distribuições e a faixa de λ. O gráfico mostra uma curva por distribuição, todas com a mesma média."
        loadingText="Calculando as séries"
      >
        {(result) => {
          const title = experimentTitle("services", model, {});
          return (
            <>
              <SaveButton
                suggestedTitle={title}
                build={(t) => experimentRecord("services", model, lastRequest.current, result, t ?? title)}
              />
              <ServicesResult result={result} model={model} />
            </>
          );
        }}
      </ResultArea>
    </div>
  );
}

export function ServicesResult({ result, model }: { result: ServicesComparisonResponse; model: ExperimentModelKey }) {
  const colors = useThemeColors();
  const [metric, setMetric] = useState<MetricName>("Wq");
  const has = (n: MetricName) => result.series.some((s) => s.points.some((p) => p.metrics && n in p.metrics));
  const shown = has(metric) ? metric : "rho";
  const lines = useMemo(() => serviceLines(result.series, shown), [result, shown]);
  const chart = useMemo(() => comparisonChart(lines, shown, colors), [lines, shown, colors]);
  const notes = describeServiceLimits(result.series);
  const anyPoint = lines.some((l) => l.y.some((v) => v !== null));
  const scale = metricScale(shown);

  return (
    <>
      {notes.length > 0 && (
        <div className="banner banner-warning" role="status">
          <IconAlertTriangle size={18} aria-hidden="true" />
          <div>
            {notes.map((n) => <div key={n}>{n}</div>)}
            <div className="banner-detail">Esses pontos não aparecem nas curvas.</div>
          </div>
        </div>
      )}
      <div className="exp-controls">
        <MetricSelect id="services-metric" model={model} value={shown} available={has} onChange={setMetric} />
      </div>
      {anyPoint ? (
        <section className="block">
          <p className="sub">
            Uma curva por distribuição, calculada pela fórmula de Pollaczek-Khinchine: com a mesma média,
            quanto maior o CV, maior a espera.
          </p>
          <PlotlyChart data={chart.data} layout={chart.layout} label={`${metricTitle(shown)} por distribuição de serviço`} />
        </section>
      ) : (
        <p className="empty-note">Nenhum ponto pôde ser calculado, então não há curva para mostrar.</p>
      )}
      <div className="table-wrap">
        <table className="table">
          <caption className="sr-only">{metricTitle(shown)} por λ e distribuição de serviço</caption>
          <thead>
            <tr>
              <th scope="col">λ (req/s)</th>
              {result.series.map((s) => <th key={serviceLabel(s.service)} scope="col" className="num">{serviceLabel(s.service)}</th>)}
            </tr>
          </thead>
          <tbody>
            {result.series[0].points.map((p, row) => (
              <tr key={p.value}>
                <th scope="row">{formatNumber(p.value)}</th>
                {result.series.map((s) => {
                  const cell = s.points[row];
                  const value = cell.status === "ok" && cell.metrics ? cell.metrics[shown] : null;
                  return (
                    <td key={serviceLabel(s.service)} className="num" title={cell.message ?? undefined}>
                      {value === null ? "—" : formatMetric(shown, value, { unit: false })}
                    </td>
                  );
                })}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {scale === 100 && <p className="note">Probabilidades e utilização em %.</p>}
    </>
  );
}
