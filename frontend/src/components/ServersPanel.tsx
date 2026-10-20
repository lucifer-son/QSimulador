import { IconAlertTriangle } from "@tabler/icons-react";
import { useEffect, useMemo, useRef, useState, type FormEvent } from "react";
import { runServerComparison, type ServerComparisonResponse } from "../api/experiments";
import { describeServerLimits, metricScale, serverLines, serversChart } from "../charts/experiments";
import {
  buildServersBody, experimentFieldErrors, parseServerList, suggestRange, suggestServers,
  type ExpErrors, type RangeText, type SystemText,
} from "../domain/experiments";
import { formatMetric, formatNumber } from "../domain/format";
import { MODELS } from "../domain/models";
import type { MarkovModelKey, MetricName } from "../domain/types";
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
  model: MarkovModelKey;
  system: SystemText;
}

/** Faixa de λ que cobre o maior número de servidores da lista (onde ele satura). */
function suggestLambdaRange(system: SystemText, serversText: string): RangeText {
  const list = parseServerList(serversText) ?? [];
  const largest = Math.max(1, ...list.filter((n) => n >= 1));
  // Sempre como M/M/c (que tem servidores), mesmo com o Laboratório no M/M/1.
  return suggestRange("lambda", "mmc", { ...system, servers: String(largest) });
}

export function ServersPanel({ active, model, system }: Props) {
  const [serversText, setServersText] = useState(() => suggestServers(model, system));
  const [range, setRange] = useState<RangeText>(() => suggestLambdaRange(system, suggestServers(model, system)));
  const [errors, setErrors] = useState<ExpErrors>({});
  const { state, run, cancel } = useExperiment<ServerComparisonResponse>();
  const lastRequest = useRef<unknown>(null);   // o pedido que gerou o resultado, para o histórico

  useEffect(() => {
    if (state.status === "error") setErrors(experimentFieldErrors(state.error.fields, state.error.code));
  }, [state]);

  const submit = (e: FormEvent) => {
    e.preventDefault();
    const built = buildServersBody(model, system, serversText, range);
    if (!built.ok) {
      setErrors(built.errors);
      return;
    }
    setErrors({});
    lastRequest.current = built.body;
    void run((signal) => runServerComparison(built.body, signal));
  };
  const edit = (field: keyof RangeText) => (value: string) => {
    setRange((r) => ({ ...r, [field]: value }));
    setErrors(({ [field]: _gone, ...rest }) => rest);
  };
  const family = MODELS[model].usesCapacity ? "M/M/c/K" : "M/M/c";

  return (
    <div className="exp-grid" hidden={!active} role="tabpanel" id="exp-panel-servers" aria-labelledby="exp-tab-servers">
      <form className="panel params" aria-label="Parâmetros da comparação de servidores" onSubmit={submit}>
        <p className="sub">
          Compara o desempenho com números diferentes de servidores sob a mesma carga ({family}, cada servidor com taxa μ).
        </p>
        <FixedParameters model={model} system={system} skip="servers" />

        <h2 className="group-title">Comparação</h2>
        <TextField
          id="servers-list" label="Servidores a comparar" value={serversText} error={errors.serversList}
          hint="De 2 a 8 valores, ex.: 1, 2, 4"
          onChange={(v) => { setServersText(v); setErrors(({ serversList: _gone, ...rest }) => rest); }}
        />
        <div className="grid2 spaced">
          <TextField id="servers-start" label="λ inicial (req/s)" value={range.start} error={errors.start} onChange={edit("start")} />
          <TextField id="servers-end" label="λ final (req/s)" value={range.end} error={errors.end} onChange={edit("end")} />
          <TextField id="servers-step" label="Passo de λ" value={range.step} error={errors.step} onChange={edit("step")} />
          <button
            type="button" className="btn btn-small suggest"
            onClick={() => {
              setServersText(suggestServers(model, system));
              setRange(suggestLambdaRange(system, suggestServers(model, system)));
              setErrors({});
            }}
          >
            Sugerir valores
          </button>
        </div>
        <div className="actions spaced">
          <RunButtons busy={state.status === "loading"} label="Comparar servidores" onCancel={cancel} />
        </div>
      </form>

      <ResultArea
        state={state}
        idleTitle="Compare números de servidores"
        idleText="Informe quais valores de c comparar e a faixa de λ. O gráfico mostra uma curva por número de servidores."
        loadingText="Calculando as séries"
      >
        {(result) => {
          const title = experimentTitle("servers", model, {});
          return (
            <>
              <SaveButton
                suggestedTitle={title}
                build={(t) => experimentRecord("servers", model, lastRequest.current, result, t ?? title)}
              />
              <ServersResult result={result} model={model} />
            </>
          );
        }}
      </ResultArea>
    </div>
  );
}

export function ServersResult({ result, model }: { result: ServerComparisonResponse; model: MarkovModelKey }) {
  const colors = useThemeColors();
  const [metric, setMetric] = useState<MetricName>("W");
  const has = (n: MetricName) => result.series.some((s) => s.points.some((p) => p.metrics && n in p.metrics));
  const shown = has(metric) ? metric : "rho";
  const lines = useMemo(() => serverLines(result.series, shown), [result, shown]);
  const chart = useMemo(() => serversChart(lines, shown, colors), [lines, shown, colors]);
  const notes = describeServerLimits(result.series);
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
        <MetricSelect id="servers-metric" model={model} value={shown} available={has} onChange={setMetric} />
      </div>
      {anyPoint ? (
        <section className="block">
          <p className="sub">Uma curva por número de servidores, calculada com o modelo analítico.</p>
          <PlotlyChart data={chart.data} layout={chart.layout} label={`${metricTitle(shown)} por número de servidores`} />
        </section>
      ) : (
        <p className="empty-note">Nenhum ponto pôde ser calculado, então não há curva para mostrar.</p>
      )}
      <div className="table-wrap">
        <table className="table">
          <caption className="sr-only">{metricTitle(shown)} por λ e número de servidores</caption>
          <thead>
            <tr>
              <th scope="col">λ (req/s)</th>
              {result.series.map((s) => <th key={s.servers} scope="col" className="num">c = {s.servers}</th>)}
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
                    <td key={s.servers} className="num" title={cell.message ?? undefined}>
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
