import { useEffect, useMemo, useState } from "react";
import {
  fetchDistribution, fetchSensitivityCurve, type DistributionResponse, type SensitivityCurve,
} from "../api/analysis";
import { ApiError } from "../api/client";
import { sensitivityChart, stateChart, tailChart } from "../charts/analysis";
import { analysisConfig, hasDistributions } from "../domain/analysis";
import type { ViewResult } from "../domain/types";
import { useThemeColors } from "../hooks/useThemeColors";
import { PlotlyChart } from "./PlotlyChart";

const num = (x: number | null | undefined, digits = 4): string =>
  x === null || x === undefined ? "—" : x.toLocaleString("pt-BR", { maximumSignificantDigits: digits });
const pct = (x: number): string => `${(x * 100).toLocaleString("pt-BR", { maximumFractionDigits: 1 })} %`;

type State =
  | { status: "loading" }
  | { status: "error"; error: ApiError }
  | { status: "success"; distribution: DistributionResponse; curve: SensitivityCurve };

/** Distribuições do Laboratório (Fase 13): P(n), P(Wq > t) e Wq × λ para a configuração do resultado atual. */
export function DistributionsTab({ result }: { result: ViewResult }) {
  const colors = useThemeColors();
  const [verify, setVerify] = useState(false);
  const [logTail, setLogTail] = useState(false);
  const [logCurve, setLogCurve] = useState(false);
  const [state, setState] = useState<State>({ status: "loading" });
  const applicable = hasDistributions(result.modelKey);

  useEffect(() => {
    if (!applicable) return;
    const controller = new AbortController();
    setState({ status: "loading" });
    const config = analysisConfig(result);
    const simulation = result.seed !== undefined ? { seed: result.seed } : {};
    Promise.all([
      fetchDistribution({ ...config, simulate: verify, simulation }, controller.signal),
      fetchSensitivityCurve(config, controller.signal),
    ]).then(
      ([distribution, curve]) => setState({ status: "success", distribution, curve }),
      (e: unknown) => {
        if (controller.signal.aborted) return;
        setState({ status: "error", error: e instanceof ApiError ? e : new ApiError("http", "Erro inesperado.") });
      },
    );
    return () => controller.abort();
  }, [result, applicable, verify]);

  const ready = state.status === "success" ? state : null;
  const states = useMemo(() => (ready?.distribution.states ? stateChart(ready.distribution.states, colors) : null), [ready, colors]);
  const tail = useMemo(
    () => (ready ? tailChart(ready.distribution.wait_closed_form, ready.distribution.wait_simulation, colors, logTail) : null),
    [ready, colors, logTail],
  );
  const curve = useMemo(() => (ready ? sensitivityChart(ready.curve, colors, logCurve) : null), [ready, colors, logCurve]);

  if (!applicable) {
    return (
      <section className="block">
        <p className="sub">
          O Erlang-B é um sistema de perda: não há fila, então não há P(Wq &gt; t) nem Wq. A distribuição dos clientes
          no sistema é a de Erlang (truncada em c), mostrada nas métricas.
        </p>
      </section>
    );
  }
  if (state.status === "loading") {
    return <div className="state" role="status"><div className="spinner" aria-hidden="true" /><p>Calculando as distribuições…</p></div>;
  }
  if (state.status === "error") return <p role="alert" className="field-error">{state.error.message}</p>;

  const { distribution, curve: sens } = state;
  const closed = distribution.wait_closed_form;
  const sim = distribution.wait_simulation;
  const canVerify = closed !== null;     // M/M/1 e M/M/c: fórmula fechada, simulação opcional

  return (
    <div className="distributions">
      <section className="block">
        <h3>Número de clientes no sistema, P(n)</h3>
        {distribution.states && states ? (
          <>
            <PlotlyChart data={states.data} layout={states.layout} label="Distribuição do número de clientes no sistema P(n)" />
            <p className="sub">
              P(0) = {num(distribution.states.p0)} · L = {num(distribution.states.mean)}
              {distribution.states.capacity !== null && <> · P(bloqueio) = P(n = K) = {num(distribution.states.p_block)}</>}
              {distribution.states.omitted_mass > 1e-6 && <> · massa fora do gráfico: {num(distribution.states.omitted_mass, 2)}</>}
            </p>
          </>
        ) : (
          <p className="sub">{distribution.states_note}</p>
        )}
      </section>

      <section className="block">
        <h3>Tempo de espera, P(Wq &gt; t)</h3>
        {tail && <PlotlyChart data={tail.data} layout={tail.layout} label="Probabilidade de a espera passar de t" />}
        <div className="field inline">
          <label><input type="checkbox" checked={logTail} onChange={(e) => setLogTail(e.target.checked)} /> Escala logarítmica</label>
          {canVerify && (
            <label><input type="checkbox" checked={verify} onChange={(e) => setVerify(e.target.checked)} /> Conferir com a simulação</label>
          )}
        </div>
        <p className="sub">
          {distribution.wait_note}
          {closed && <> P(esperar) = {pct(closed.p_wait)}; espera mediana {num(closed.percentiles.p50)} s e 95 % dos clientes esperam até {num(closed.percentiles.p95)} s.</>}
          {sim && !closed && <> P(esperar) ≈ {pct(sim.p_wait.mean)}; 95 % dos clientes esperam até ≈ {num(sim.percentiles.p95.mean)} s ({sim.replications} réplicas, semente {sim.seed}).</>}
        </p>
      </section>

      <section className="block">
        <h3>Sensibilidade: Wq × λ</h3>
        {curve && <PlotlyChart data={curve.data} layout={curve.layout} label="Tempo médio de espera em função da taxa de chegada" />}
        <div className="field inline">
          <label><input type="checkbox" checked={logCurve} onChange={(e) => setLogCurve(e.target.checked)} /> Escala logarítmica</label>
        </div>
        <p className="sub">
          O losango é a configuração atual (λ = {num(sens.current.value)}, Wq = {num(sens.current.wq)} s, ρ = {num(sens.current.rho, 3)}).
          {sens.stability_limit !== null && <> A curva para em ρ = 0,99 (λ = {num(sens.stability_limit)}): acima disso a fila cresce sem limite.</>}
        </p>
      </section>
    </div>
  );
}
