import { IconAlertTriangle, IconCheck, IconInfoCircle, IconX } from "@tabler/icons-react";
import { useMemo, useState } from "react";
import type { MultipleComparison, ScenarioRow, ScenarioSettings } from "../api/scenarios";
import { diffChart } from "../charts/scenarios";
import { formatMetric } from "../domain/format";
import { METRIC_INFO } from "../domain/metrics";
import {
  describeChanges, formatDelta, formatRelative, metricsOf, VERDICT_LABEL,
} from "../domain/scenarios";
import type { MetricName } from "../domain/types";
import { useThemeColors } from "../hooks/useThemeColors";
import { PlotlyChart } from "./PlotlyChart";

/** O resultado da comparação (completo, ou só o que já chegou do fluxo). Também reaberto pelo Histórico. */
export interface ScenariosViewData {
  settings: ScenarioSettings;
  multiple_comparison: MultipleComparison;
  base: ScenarioRow | null;
  scenarios: ScenarioRow[];
}

const pct = (level: number) => `${(level * 100).toLocaleString("pt-BR", { maximumFractionDigits: 2 })}%`;
const num = (name: MetricName, v: number | null | undefined) => (v === null || v === undefined ? "—" : formatMetric(name, v, { precise: true, unit: false }));

function half(low: number | null | undefined, high: number | null | undefined): number | null {
  return low === null || low === undefined || high === null || high === undefined ? null : (high - low) / 2;
}

function SituationTags({ row }: { row: ScenarioRow }) {
  return (
    <>
      {row.status === "unstable" && <span className="tag tag-bad" title={row.message ?? undefined}><IconX size={14} aria-hidden="true" />instável</span>}
      {row.status === "error" && <span className="tag tag-bad" title={row.message ?? undefined}><IconX size={14} aria-hidden="true" />sem amostra</span>}
      {row.status === "ok" && <span className="tag tag-ok"><IconCheck size={14} aria-hidden="true" />simulado</span>}
      {row.alerts.filter((a) => a.code === "at_risk").map((a) => (
        <span key={a.code} className="tag tag-warn" title={a.message}><IconAlertTriangle size={14} aria-hidden="true" />em risco</span>
      ))}
      {row.alerts.some((a) => a.code === "approximation") && (
        <span className="tag tag-warn" title="Aproximação de Allen–Cunneen fora da faixa confortável."><IconAlertTriangle size={14} aria-hidden="true" />aproximação</span>
      )}
    </>
  );
}

function rowClass(row: ScenarioRow): string | undefined {
  if (row.status !== "ok") return "row-bad";
  return row.alerts.some((a) => a.code === "at_risk") ? "row-warn" : undefined;
}

export function ScenariosView({ data, progress }: { data: ScenariosViewData; progress?: { completed: number; total: number } }) {
  const colors = useThemeColors();
  const rows = useMemo(() => (data.base ? [data.base, ...data.scenarios] : data.scenarios), [data]);
  const available = useMemo(() => metricsOf(data), [data]);
  const [chosen, setChosen] = useState<MetricName>("Wq");
  const metric: MetricName = available.includes(chosen) ? chosen : (available[0] ?? "Wq");
  const { settings, multiple_comparison: multi } = data;

  const chart = useMemo(
    () => diffChart(data.scenarios, metric, colors, settings.diff_confidence_level),
    [data.scenarios, metric, colors, settings.diff_confidence_level],
  );
  const hasDiff = data.scenarios.some((r) => r.metrics[metric]?.diff);
  const warnings = rows.flatMap((r) => r.alerts.map((a) => ({ name: r.name, ...a })));

  if (rows.length === 0) {
    return progress && progress.total > 0 ? <p className="note">{progress.completed} de {progress.total} simulações concluídas.</p> : null;
  }

  return (
    <>
      {progress && progress.total > 0 && (
        <div className="progress-wrap">
          <div
            className="progress" role="progressbar" aria-label="Progresso da comparação"
            aria-valuemin={0} aria-valuemax={progress.total} aria-valuenow={progress.completed}
          >
            <div className="progress-bar" style={{ width: `${(100 * progress.completed) / progress.total}%` }} />
          </div>
          <p className="note">{progress.completed} de {progress.total} simulações concluídas. Cancelar interrompe o que falta.</p>
        </div>
      )}

      <div className={multi.individual_intervals ? "banner banner-warning" : "banner banner-info"} role="note">
        {multi.individual_intervals ? <IconAlertTriangle size={18} aria-hidden="true" /> : <IconInfoCircle size={18} aria-hidden="true" />}
        <div>
          {multi.individual_intervals && <strong>ICs individuais. </strong>}
          {multi.note}
          <div className="banner-detail">
            As réplicas usam as mesmas sementes em todos os cenários (números aleatórios comuns), por isso a diferença é pareada.
            “Inconclusivo” não significa igual: o IC contém 0, e talvez falte réplica ou tempo para distinguir.
          </div>
        </div>
      </div>

      <p className="note">
        Semente {settings.seed} · {settings.replications} réplicas · T = {settings.simulation_time} s · warm-up {settings.warmup_time} s ·
        IC dos cenários {pct(settings.confidence_level)} · IC das diferenças {pct(settings.diff_confidence_level)}
      </p>

      <div className="field inline">
        <label htmlFor="scn-metric">Métrica</label>
        <select id="scn-metric" value={metric} onChange={(e) => setChosen(e.target.value as MetricName)}>
          {available.map((m) => <option key={m} value={m}>{METRIC_INFO[m].label}</option>)}
        </select>
      </div>

      {hasDiff && (
        <section className="block">
          <p className="sub">Diferença de cada cenário contra a base ({METRIC_INFO[metric].label}), com o IC pareado. Ponto cheio: diferença significativa.</p>
          <PlotlyChart data={chart.data} layout={chart.layout} label={`Diferença de ${METRIC_INFO[metric].label} contra a base`} />
        </section>
      )}

      <div className="table-wrap">
        <table className="table">
          <caption className="sr-only">Comparação de {METRIC_INFO[metric].label} entre a base e os cenários</caption>
          <thead>
            <tr>
              <th scope="col">Cenário</th>
              <th scope="col">Situação</th>
              <th scope="col" className="num">Simulação (média ± IC)</th>
              <th scope="col" className="num">Analítico</th>
              <th scope="col" className="num">Δ analítico</th>
              <th scope="col" className="num">Δ simulada (IC pareado)</th>
              <th scope="col" className="num">Variação</th>
              <th scope="col">Veredito</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((row) => {
              const m = row.metrics[metric];
              const hw = half(m?.simulation?.ci_low, m?.simulation?.ci_high);
              const dhw = half(m?.diff?.ci_low, m?.diff?.ci_high);
              return (
                <tr key={row.index} className={rowClass(row)}>
                  <th scope="row">
                    {row.name}
                    <div className="cell-sub">{row.model_label}{row.role === "base" ? " · base" : ` · ${describeChanges(row)}`}</div>
                  </th>
                  <td><SituationTags row={row} /></td>
                  <td className="num">{m?.simulation ? `${num(metric, m.simulation.mean)}${hw === null ? "" : ` ± ${num(metric, hw)}`}` : "—"}</td>
                  <td className="num">{num(metric, m?.analytic)}</td>
                  <td className="num">{m?.analytic_diff === null || m?.analytic_diff === undefined ? "—" : formatDelta(metric, m.analytic_diff)}</td>
                  <td className="num">
                    {m?.diff ? `${formatDelta(metric, m.diff.mean)}${dhw === null ? "" : ` ± ${num(metric, dhw).replace("%", "")}`}` : "—"}
                  </td>
                  <td className="num">{formatRelative(m?.relative_change)}</td>
                  <td>
                    {m?.verdict ? (
                      <span className={m.verdict === "inconclusive" ? "tag" : "tag tag-info"}>{VERDICT_LABEL[m.verdict]}</span>
                    ) : "—"}
                    {m?.analytic_diff_in_ci === false && <div className="cell-sub">analítico fora do IC</div>}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
      <p className="note">“—”: a métrica não existe no modelo do cenário, ou o cenário não foi simulado. Δ = cenário − base.</p>

      {warnings.length > 0 && (
        <ul className="scn-alerts" aria-label="Avisos dos cenários">
          {warnings.map((w, i) => (
            <li key={`${w.name}-${w.code}-${i}`} className={w.level === "error" ? "alert-bad" : "alert-warn"}>
              <strong>{w.name}:</strong> {w.message}
            </li>
          ))}
        </ul>
      )}
    </>
  );
}
