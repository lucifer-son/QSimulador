import { IconAlertTriangle, IconCheck, IconInfoCircle, IconX } from "@tabler/icons-react";
import { useMemo, useState } from "react";
import type {
  ApproachInfo, ApproachKey, CompareMetric, CompareResult, PlanRow, Scope, SweepResult, TrafficAlert, TrafficReference,
  TrafficResult, ValidationApproach, VideoValidation,
} from "../api/traffic";
import {
  approachColor, planDelayChart, queueSeriesChart, sweepChart, validationDeparturesChart, validationQueueChart,
} from "../charts/traffic";
import {
  alertTone, COMPARE_METRICS, formatDelta, formatMetricValue, formatSaturation, formatSeconds, formatSummary,
  HEADLINE_METRICS, METRICS, NOT_INFORMED_LABEL, phaseText, SCOPE_LABEL, VERDICT_TEXT, verdictTone,
} from "../domain/traffic";
import { useThemeColors } from "../hooks/useThemeColors";
import { PlotlyChart } from "./PlotlyChart";

const pct = (v: number) => `${(v * 100).toLocaleString("pt-BR", { maximumFractionDigits: 2 })}%`;
const num = (v: number | null | undefined, digits = 2) =>
  v === null || v === undefined ? "—" : v.toLocaleString("pt-BR", { minimumFractionDigits: digits, maximumFractionDigits: digits });

export function AlertList({ alerts, label = "Avisos" }: { alerts: TrafficAlert[]; label?: string }) {
  if (alerts.length === 0) return null;
  return (
    <ul className="scn-alerts" aria-label={label}>
      {alerts.map((a, i) => (
        <li key={`${a.code}-${a.approach ?? "x"}-${a.field ?? ""}-${i}`} className={alertTone(a) === "bad" ? "alert-bad" : alertTone(a) === "info" ? "alert-info" : "alert-warn"}>
          {a.message}
        </li>
      ))}
    </ul>
  );
}

export function Progress({ completed, total, what }: { completed: number; total: number; what: string }) {
  if (total <= 0) return null;
  return (
    <div className="progress-wrap">
      <div className="progress" role="progressbar" aria-label={`Progresso: ${what}`} aria-valuemin={0} aria-valuemax={total} aria-valuenow={completed}>
        <div className="progress-bar" style={{ width: `${(100 * completed) / total}%` }} />
      </div>
      <p className="note">{completed} de {total} {what} concluídos. Cancelar interrompe o que falta.</p>
    </div>
  );
}

// ---------- simulação ----------

function SaturationTag({ x }: { x: number }) {
  if (x >= 1) return <span className="tag tag-bad" title="Demanda maior que a capacidade do verde: a fila cresce."><IconX size={14} aria-hidden="true" />x = {formatSaturation(x)}</span>;
  if (x >= 0.9) return <span className="tag tag-warn" title="Perto da saturação."><IconAlertTriangle size={14} aria-hidden="true" />x = {formatSaturation(x)}</span>;
  return <span className="tag tag-ok"><IconCheck size={14} aria-hidden="true" />x = {formatSaturation(x)}</span>;
}

function ApproachCards({ approaches }: { approaches: ApproachInfo[] }) {
  return (
    <div className="cards" role="group" aria-label="Aproximações">
      {approaches.map((a) => (
        <div key={a.key} className="card">
          <div className="card-label">{a.name}</div>
          <div className="card-value"><SaturationTag x={a.saturation} /></div>
          <div className="card-sub">capacidade {num(a.capacity * 60, 1)} veíc./min · chegada {num(a.arrival_rate * 60, 1)} veíc./min</div>
          <div className="card-sub">intervalo {a.headway.label}, média {num(a.headway.mean, 2)} s{a.headway.cv > 0 ? `, CV ${num(a.headway.cv, 2)}` : ""}</div>
          {a.not_informed.length > 0 && (
            <div className="card-sub">sem medição: {a.not_informed.map((n) => NOT_INFORMED_LABEL[n] ?? n).join(", ")}</div>
          )}
        </div>
      ))}
    </div>
  );
}

function ReferenceTable({ reference, result }: { reference: TrafficReference; result: TrafficResult }) {
  const rows = (["a1", "a2"] as ApproachKey[]).map((k) => {
    const sim = result.metrics[k].delay_censored;
    const ref = reference[k];
    const inside = sim && sim.ci_low != null && sim.ci_high != null ? ref.delay_censored >= sim.ci_low && ref.delay_censored <= sim.ci_high : null;
    return { k, sim, ref, inside };
  });
  const web = reference.webster_cycle;
  return (
    <section className="block" aria-labelledby="traffic-ref-title">
      <h3 id="traffic-ref-title">Conferência com a fórmula de Webster (aproximação)</h3>
      <p className="sub">
        Ordem de grandeza do atraso, sem simulação. Vale para x &lt; 1; com x ≥ 1 usa-se o modelo fluido, que ignora a aleatoriedade e subestima
        perto de x = 1. Não é um resultado exato.
      </p>
      <div className="table-wrap">
        <table className="table">
          <caption className="sr-only">Atraso simulado e aproximação analítica por aproximação</caption>
          <thead>
            <tr>
              <th scope="col">Aproximação</th><th scope="col" className="num">x</th><th scope="col">Método</th>
              <th scope="col" className="num">Atraso uniforme</th><th scope="col" className="num">Atraso (analítico)</th>
              <th scope="col" className="num">Atraso (simulação)</th><th scope="col">Analítico no IC?</th>
            </tr>
          </thead>
          <tbody>
            {rows.map(({ k, sim, ref, inside }) => (
              <tr key={k}>
                <th scope="row">{result.approaches.find((a) => a.key === k)?.name ?? SCOPE_LABEL[k]}</th>
                <td className="num">{formatSaturation(ref.saturation)}</td>
                <td>{ref.kind === "webster" ? "Webster" : "Fluido"}</td>
                <td className="num">{formatSeconds(ref.uniform_delay)}</td>
                <td className="num">{formatSeconds(ref.delay_censored)}</td>
                <td className="num">{sim ? formatSeconds(sim.mean) : "—"}</td>
                <td>{inside === null ? "—" : inside ? <span className="tag tag-ok">sim</span> : <span className="tag">não</span>}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {web && (
        <p className="note">
          Ciclo ótimo de Webster para estas demandas (aproximação): {num(web.cycle, 0)} s, com tempo perdido total de {num(web.lost_time, 1)} s e
          soma das razões críticas Y = {num(web.critical_ratio_sum, 2)}. O ciclo atual é de {num(result.plan.cycle, 0)} s.
        </p>
      )}
    </section>
  );
}

export function TrafficSimulationView({ result }: { result: TrafficResult }) {
  const colors = useThemeColors();
  const names = useMemo(() => ({
    a1: result.approaches.find((a) => a.key === "a1")?.name ?? "Aproximação 1",
    a2: result.approaches.find((a) => a.key === "a2")?.name ?? "Aproximação 2",
  }), [result.approaches]);
  const chart = useMemo(() => (result.series ? queueSeriesChart(result.series, names, colors) : null), [result.series, names, colors]);
  const x = result.metrics.x;
  const s = result.settings;
  return (
    <>
      <p className="sub">
        Ciclo de {num(result.plan.cycle, 0)} s ({result.plan.phases.map(phaseText).join(" | ")}), {s.replications} réplicas de {num(s.simulation_time / 60, 0)} min,
        semente {s.seed}. Intervalos de {pct(s.confidence_level)} de confiança.
      </p>
      <AlertList alerts={result.alerts} />
      <ApproachCards approaches={result.approaches} />
      <div className="cards" role="group" aria-label="Resumo do cruzamento">
        <div className="card">
          <div className="card-label">Atraso médio por veículo</div>
          <div className="card-value">{formatSeconds(x.delay_censored?.mean)}</div>
          <div className="card-sub">com pendentes (limite inferior)</div>
        </div>
        <div className="card">
          <div className="card-label">Vazão atendida</div>
          <div className="card-value">{formatMetricValue("throughput", x.throughput?.mean)}</div>
          <div className="card-sub">veículos por minuto</div>
        </div>
        <div className="card">
          <div className="card-label">Fila média total</div>
          <div className="card-value">{formatMetricValue("queue_mean", x.queue_mean?.mean)}</div>
          <div className="card-sub">veículos</div>
        </div>
        <div className="card">
          <div className="card-label">Pendentes ao fim</div>
          <div className="card-value">{formatMetricValue("pending", x.pending?.mean)}</div>
          <div className="card-sub">veículos ainda esperando</div>
        </div>
      </div>

      <section className="block" aria-labelledby="traffic-metrics-title">
        <h3 id="traffic-metrics-title">Métricas por aproximação</h3>
        <p className="sub">Média das réplicas e IC da média, entre colchetes.</p>
        <div className="table-wrap">
          <table className="table">
            <caption className="sr-only">Métricas simuladas do cruzamento e de cada aproximação</caption>
            <thead>
              <tr>
                <th scope="col">Métrica</th>
                {(["a1", "a2", "x"] as Scope[]).map((k) => (
                  <th key={k} scope="col" className="num">{k === "x" ? "Cruzamento" : names[k]}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {HEADLINE_METRICS.map((m) => (
                <tr key={m}>
                  <th scope="row" title={METRICS[m].hint}>{METRICS[m].label} <span className="cell-sub">{METRICS[m].unit}</span></th>
                  {(["a1", "a2", "x"] as Scope[]).map((k) => (
                    <td key={k} className="num">{k === "x" && (m === "queue_end" || m === "queue_max" || m === "stopped_fraction" || m === "overflow_cycles") ? "—" : formatSummary(m, result.metrics[k][m])}</td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <p className="note">
          O atraso “com pendentes” inclui os veículos que ainda esperavam ao fim da simulação, contados só até T. “Concluídos” considera apenas quem já cruzou
          e parece melhor quando a fila está crescendo.
        </p>
      </section>

      {chart && (
        <section className="block" aria-labelledby="traffic-queue-title">
          <h3 id="traffic-queue-title">Fila ao longo do tempo</h3>
          <p className="sub">Média das réplicas e IC da média. A fila cresce no vermelho e se dissipa no verde de cada aproximação.</p>
          <PlotlyChart data={chart.data} layout={chart.layout} label="Tamanho médio da fila de cada aproximação ao longo do tempo, com intervalo de confiança" />
        </section>
      )}
      <ReferenceTable reference={result.reference} result={result} />
    </>
  );
}

// ---------- comparação de planos ----------

function VerdictTag({ metric, name }: { metric: CompareMetric | undefined; name: string }) {
  if (!metric?.diff || !metric.verdict) return <span>—</span>;
  const tone = verdictTone(metric.verdict, metric.better);
  const cls = tone === "good" ? "tag tag-ok" : tone === "bad" ? "tag tag-bad" : "tag";
  return (
    <div>
      <div>{formatDelta(name, metric.diff)} <span className="cell-sub">[{formatDelta(name, { ...metric.diff, mean: metric.diff.ci_low ?? metric.diff.mean })}; {formatDelta(name, { ...metric.diff, mean: metric.diff.ci_high ?? metric.diff.mean })}]</span></div>
      <span className={cls}>{VERDICT_TEXT[metric.verdict]}</span>
    </div>
  );
}

type RowMetrics = Record<Scope, Record<string, CompareMetric>>;
const metricsOfRow = (row: PlanRow): RowMetrics | null => (row.status === "ok" ? (row.metrics as RowMetrics) : null);

export function TrafficCompareView({ data, names }: { data: Pick<CompareResult, "settings" | "multiple_comparison"> & { base: PlanRow | null; plans: PlanRow[] }; names?: Record<ApproachKey, string> }) {
  const colors = useThemeColors();
  const [metric, setMetric] = useState("delay_censored");
  const rows = useMemo(() => [...(data.base ? [data.base] : []), ...data.plans], [data.base, data.plans]);
  const chart = useMemo(() => (data.base ? planDelayChart({ settings: data.settings, multiple_comparison: data.multiple_comparison, base: data.base, plans: data.plans }, colors) : null), [data, colors]);
  const level = pct(data.multiple_comparison.confidence_level);
  const label = (k: ApproachKey) => names?.[k] ?? SCOPE_LABEL[k];
  return (
    <>
      <div className={data.multiple_comparison.correction === "none" && data.multiple_comparison.comparisons > 1 ? "banner banner-warning" : "banner banner-info"} role="note">
        <IconInfoCircle size={18} aria-hidden="true" />
        <div>{data.multiple_comparison.note}</div>
      </div>
      {chart && data.plans.length > 0 && (
        <section className="block" aria-labelledby="traffic-plans-chart">
          <h3 id="traffic-plans-chart">Atraso médio por plano</h3>
          <p className="sub">Atraso médio do cruzamento (com pendentes), com o IC de cada plano.</p>
          <PlotlyChart data={chart.data} layout={chart.layout} label="Atraso médio do cruzamento por plano semafórico, com intervalo de confiança" />
        </section>
      )}
      <div className="field inline">
        <label htmlFor="traffic-compare-metric">Métrica da tabela</label>
        <select id="traffic-compare-metric" value={metric} onChange={(e) => setMetric(e.target.value)}>
          {COMPARE_METRICS.map((m) => <option key={m} value={m}>{METRICS[m].label} ({METRICS[m].unit})</option>)}
        </select>
      </div>
      <div className="table-wrap">
        <table className="table">
          <caption className="sr-only">Planos semafóricos comparados com a referência: {METRICS[metric].label}</caption>
          <thead>
            <tr>
              <th scope="col">Plano</th><th scope="col" className="num">Ciclo</th><th scope="col" className="num">x₁ / x₂</th>
              {(["x", "a1", "a2"] as Scope[]).map((k) => (
                <th key={k} scope="col" className="num">{k === "x" ? "Cruzamento" : label(k)}<div className="cell-sub">Δ vs referência ({level})</div></th>
              ))}
            </tr>
          </thead>
          <tbody>
            {rows.map((row) => {
              const m = metricsOfRow(row);
              return (
                <tr key={row.index} className={row.status === "error" ? "row-bad" : undefined}>
                  <th scope="row">
                    {row.name}
                    <div className="cell-sub">{row.role === "base" ? "referência · " : ""}verde {num(row.phases[0].green, 0)} / {num(row.phases[1].green, 0)} s</div>
                    {row.status === "error" && <div className="cell-sub">{row.message ?? "sem amostra"}</div>}
                  </th>
                  <td className="num">{num(row.cycle, 0)} s</td>
                  <td className="num">{formatSaturation(row.saturation.a1)} / {formatSaturation(row.saturation.a2)}</td>
                  {(["x", "a1", "a2"] as Scope[]).map((k) => {
                    const cell = m?.[k]?.[metric];
                    return (
                      <td key={k} className="num">
                        <div>{formatSummary(metric, cell?.simulation)}</div>
                        {row.role === "plan" && <VerdictTag metric={cell} name={metric} />}
                      </td>
                    );
                  })}
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
      <p className="note">
        Δ = plano − referência, com IC pareado (mesmas chegadas e intervalos em todos os planos). “inconclusivo” não quer dizer igual: as réplicas feitas não bastam
        para distinguir. Verde = melhora, vermelho = piora da métrica escolhida.
      </p>
      <AlertList alerts={rows.flatMap((r) => r.alerts.filter((a) => a.code === "cycle_changed" || a.code === "oversaturated").map((a) => ({ ...a, message: `${r.name}: ${a.message}` })))} label="Avisos dos planos" />
    </>
  );
}

// ---------- varredura do verde ----------

const SWEEP_TAG: Record<string, { text: string; cls: string }> = {
  best: { text: "menor atraso", cls: "tag tag-ok" },
  indistinguishable: { text: "indistinguível do melhor", cls: "tag tag-info" },
  worse: { text: "pior que o melhor", cls: "tag" },
  better: { text: "melhor", cls: "tag tag-ok" },
  unknown: { text: "sem comparação", cls: "tag" },
};

export function TrafficSweepView({ data, names }: { data: SweepResult; names?: Record<ApproachKey, string> }) {
  const colors = useThemeColors();
  const chart = useMemo(() => sweepChart(data, colors), [data, colors]);
  const best = data.points[data.best_index];
  const indist = data.points.filter((p) => p.vs_best.verdict === "indistinguishable");
  const label = (k: ApproachKey) => names?.[k] ?? SCOPE_LABEL[k];
  return (
    <>
      <p className="sub">
        Ciclo fixo de {num(data.cycle, 0)} s, verde total de {num(data.green_total, 0)} s redistribuído entre as fases (amarelo e todo-vermelho não mudam).
        {" "}{data.settings.replications} réplicas por ponto, semente {data.settings.seed}.
      </p>
      <div className="banner banner-success" role="note">
        <IconCheck size={18} aria-hidden="true" />
        <div>
          Menor atraso médio: verde {num(best.green[0], 1)} s / {num(best.green[1], 1)} s, com {formatSeconds(best.intersection.delay_censored?.mean)} por veículo.
          {indist.length > 0 && (
            <div className="banner-detail">
              {indist.length === 1 ? "Outro ponto não se distingue" : `Outros ${indist.length} pontos não se distinguem`} dele com as réplicas feitas
              (verde da fase 1: {indist.map((p) => num(p.green[0], 1)).join(", ")} s): a curva é plana nessa região.
            </div>
          )}
        </div>
      </div>
      <section className="block" aria-labelledby="traffic-sweep-chart">
        <h3 id="traffic-sweep-chart">Atraso pela divisão do verde</h3>
        <PlotlyChart data={chart.data} layout={chart.layout} label="Atraso médio do cruzamento em função da divisão do verde entre as duas fases, com intervalo de confiança" />
      </section>
      <div className="table-wrap">
        <table className="table">
          <caption className="sr-only">Pontos da varredura da divisão do verde</caption>
          <thead>
            <tr>
              <th scope="col" className="num">Verde 1 / 2 (s)</th><th scope="col" className="num">x₁ / x₂</th>
              <th scope="col" className="num">Atraso do cruzamento (s)</th>
              <th scope="col" className="num">{label("a1")} (s)</th><th scope="col" className="num">{label("a2")} (s)</th>
              <th scope="col" className="num">Ciclos com fila (1 / 2)</th><th scope="col">Contra o melhor</th>
            </tr>
          </thead>
          <tbody>
            {data.points.map((p) => (
              <tr key={p.index} className={p.index === data.best_index ? "row-best" : p.saturation.a1 >= 1 || p.saturation.a2 >= 1 ? "row-warn" : undefined}>
                <th scope="row" className="num">{num(p.green[0], 1)} / {num(p.green[1], 1)}</th>
                <td className="num">{formatSaturation(p.saturation.a1)} / {formatSaturation(p.saturation.a2)}</td>
                <td className="num">{formatSummary("delay_censored", p.intersection.delay_censored)}</td>
                <td className="num">{formatMetricValue("delay_censored", p.a1.delay_censored?.mean)}</td>
                <td className="num">{formatMetricValue("delay_censored", p.a2.delay_censored?.mean)}</td>
                <td className="num">{formatMetricValue("overflow_cycles", p.a1.overflow_cycles?.mean)}% / {formatMetricValue("overflow_cycles", p.a2.overflow_cycles?.mean)}%</td>
                <td><span className={(SWEEP_TAG[p.vs_best.verdict] ?? SWEEP_TAG.unknown).cls}>{(SWEEP_TAG[p.vs_best.verdict] ?? SWEEP_TAG.unknown).text}</span></td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <p className="note">{data.note} Linhas em amarelo têm alguma aproximação com x ≥ 1 (a fila cresce).</p>
      {data.webster_cycle && (
        <p className="note">Referência aproximada: o ciclo ótimo de Webster para estas demandas é de {num(data.webster_cycle.cycle, 0)} s (Y = {num(data.webster_cycle.critical_ratio_sum, 2)}).</p>
      )}
    </>
  );
}

// ---------- validação com o vídeo ----------

function ErrorsRow({ label, e, unit }: { label: string; e: { n: number; bias: number; mae: number; rmse: number; coverage: number } | null; unit: string }) {
  return (
    <tr>
      <th scope="row">{label} <span className="cell-sub">{unit}</span></th>
      {e ? (
        <>
          <td className="num">{e.n}</td><td className="num">{num(e.bias, 2)}</td><td className="num">{num(e.mae, 2)}</td>
          <td className="num">{num(e.rmse, 2)}</td><td className="num">{pct(e.coverage)}</td>
        </>
      ) : <td colSpan={5} className="cell-sub">sem dados observados utilizáveis</td>}
    </tr>
  );
}

function ValidationApproachView({ k, a, ids }: { k: ApproachKey; a: ValidationApproach; ids: Record<ApproachKey, string> }) {
  const colors = useThemeColors();
  const color = approachColor(colors, k);
  const queue = useMemo(() => validationQueueChart(a, ids[k], color, colors), [a, ids, k, color, colors]);
  const deps = useMemo(() => validationDeparturesChart(a, ids[k], color, colors), [a, ids, k, color, colors]);
  const t = a.departures_total;
  return (
    <section className="block" aria-labelledby={`val-${k}`}>
      <h3 id={`val-${k}`}>{ids[k]}</h3>
      <div className="table-wrap">
        <table className="table">
          <caption className="sr-only">Erros da simulação contra o observado em {ids[k]}</caption>
          <thead>
            <tr>
              <th scope="col">Comparação</th><th scope="col" className="num">Intervalos</th><th scope="col" className="num">Viés</th>
              <th scope="col" className="num">Erro médio abs.</th><th scope="col" className="num">RMSE</th><th scope="col" className="num">Observado na faixa</th>
            </tr>
          </thead>
          <tbody>
            <ErrorsRow label="Fila no fim do intervalo" e={a.queue} unit="veíc." />
            <ErrorsRow label="Saídas por intervalo" e={a.departures} unit="veíc." />
          </tbody>
        </table>
      </div>
      <p className="note">
        Total de saídas: observado {t.observed ?? "—"}, simulado {num(t.mean, 0)} (faixa {num(t.low, 0)} a {num(t.high, 0)})
        {t.relative_error !== null && t.relative_error !== undefined ? `, erro relativo ${num(t.relative_error * 100, 1)}%` : ""}.
        {a.delay && <> Atraso: observado {formatSeconds(a.delay.observed_mean)} em {a.delay.observed_n} veículos acompanhados, simulado {formatSeconds(a.delay.simulated_mean)}. {a.delay.note}</>}
      </p>
      <PlotlyChart data={queue.data} layout={queue.layout} label={`Fila observada e simulada em ${ids[k]}`} />
      <PlotlyChart data={deps.data} layout={deps.layout} label={`Saídas por intervalo, observadas e simuladas, em ${ids[k]}`} />
    </section>
  );
}

export function TrafficValidationView({ result, ids }: { result: VideoValidation; ids: Record<ApproachKey, string> }) {
  const s = result.settings;
  return (
    <>
      <div className="banner banner-info" role="note">
        <IconInfoCircle size={18} aria-hidden="true" />
        <div>
          Simulação do plano observado com {s.replications} réplicas e as chegadas do vídeo. {s.note}
        </div>
      </div>
      {result.notes.length > 0 && <ul className="scn-alerts" aria-label="Observações da validação">{result.notes.map((n) => <li key={n} className="alert-warn">{n}</li>)}</ul>}
      {(["a1", "a2"] as ApproachKey[]).map((k) => <ValidationApproachView key={k} k={k} a={result.approaches[k]} ids={ids} />)}
    </>
  );
}
