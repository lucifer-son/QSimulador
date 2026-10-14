import { IconAlertTriangle, IconDownload } from "@tabler/icons-react";
import { useMemo, useState } from "react";
import type {
  DatasetLevel, DatasetSummary, LevelsCompareResponse, RealCompareResponse,
} from "../api/realdata";
import { LEVEL_METRIC_TITLE, levelsChart, type LevelMetric } from "../charts/realdata";
import { formatInteger, formatMetric, formatNumber, formatPercentNumber } from "../domain/format";
import { MU_SOURCE_LABELS } from "../domain/realdata";
import type { MetricName } from "../domain/types";
import { useThemeColors } from "../hooks/useThemeColors";
import { PlotlyChart } from "./PlotlyChart";

const ms = (v: number) => `${formatNumber(Number(v.toFixed(2)))} ms`;
const THINK_SOURCE = { informed: "informado", interactive_law: "lei da resposta interativa: Z = N/X − R" } as const;

function Card({ label, value, sub }: { label: string; value: string; sub?: string }) {
  return (
    <div className="card">
      <div className="card-label">{label}</div>
      <div className="card-value">{value}</div>
      {sub && <div className="card-sub">{sub}</div>}
    </div>
  );
}

export function WarningList({ warnings }: { warnings: string[] }) {
  if (warnings.length === 0) return null;
  return (
    <div className="banner banner-warning" role="status">
      <IconAlertTriangle size={18} aria-hidden="true" />
      <div>{warnings.map((w) => <div key={w} className="rd-warning">{w}</div>)}</div>
    </div>
  );
}

/** Métricas empíricas do teste importado. */
export function DatasetView({ data }: { data: DatasetSummary }) {
  return (
    <section className="block" aria-label="Dados medidos">
      <h2 className="group-title">Dados medidos</h2>
      <p className="sub">
        {formatInteger(data.samples_used)} de {formatInteger(data.samples_total)} amostras usadas, janela de{" "}
        {formatNumber(Number(data.window_seconds.toFixed(1)))} s
        {data.label ? `, rótulo “${data.label}”` : ", todos os rótulos"}.
      </p>
      <div className="cards">
        <Card label="Vazão" value={`${formatNumber(Number(data.throughput.toFixed(3)))} req/s`} />
        <Card label="Tempo médio" value={ms(data.mean_ms)} sub={`desvio ${ms(data.std_ms)}`} />
        <Card label="p90 / p95 / p99" value={`${formatNumber(Number(data.p90_ms.toFixed(1)))} / ${formatNumber(Number(data.p95_ms.toFixed(1)))} / ${formatNumber(Number(data.p99_ms.toFixed(1)))}`} sub="ms" />
        <Card label="Taxa de erro" value={formatPercentNumber(data.error_rate * 100)} />
        <Card label="Usuários (allThreads)" value={data.users === null ? "—" : String(data.users)} sub={data.users_max ? `máx. ${data.users_max}` : undefined} />
      </div>
      {data.labels.length > 1 && (
        <div className="table-wrap">
          <table className="table">
            <caption className="sr-only">Métricas por rótulo</caption>
            <thead>
              <tr>
                <th scope="col">Rótulo</th><th scope="col" className="num">Amostras</th>
                <th scope="col" className="num">Média</th><th scope="col" className="num">p90</th>
                <th scope="col" className="num">Erros</th>
              </tr>
            </thead>
            <tbody>
              {data.labels.map((l) => (
                <tr key={l.label}>
                  <th scope="row">{l.label}</th>
                  <td className="num">{formatInteger(l.samples)}</td>
                  <td className="num">{ms(l.mean_ms)}</td>
                  <td className="num">{ms(l.p90_ms)}</td>
                  <td className="num">{formatPercentNumber(l.error_rate * 100)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </section>
  );
}

const METRIC_ROWS: MetricName[] = ["throughput", "W", "L", "rho"];
const ROLE = { prediction: "previsão do modelo", input: "usada como entrada" } as const;

/** Medido × analítico × simulação do modo aberto ou fechado. */
export function ComparisonView({ data }: { data: RealCompareResponse }) {
  const hasSim = data.simulation !== null;
  return (
    <section className="block" aria-label="Comparação com o modelo">
      <h2 className="group-title">Medido × modelo {data.model}</h2>
      <ul className="rd-calibration">
        <li>μ = <strong>{formatNumber(Number(data.mu.toFixed(4)))} req/s</strong> por servidor ({MU_SOURCE_LABELS[data.mu_source].toLowerCase()}); {data.servers} servidor(es)</li>
        {data.mode === "closed" && data.think_time !== null && data.think_time_source && (
          <li>N = <strong>{data.users}</strong> usuários; Z = <strong>{formatNumber(Number(data.think_time.toFixed(4)))} s</strong> ({THINK_SOURCE[data.think_time_source]})</li>
        )}
        {data.mode === "open" && data.arrival_rate !== null && (
          <li>λ = <strong>{formatNumber(Number(data.arrival_rate.toFixed(4)))} req/s</strong> (vazão medida)</li>
        )}
      </ul>
      <WarningList warnings={data.warnings} />
      <div className="table-wrap">
        <table className="table">
          <caption className="sr-only">Métricas medidas e previstas</caption>
          <thead>
            <tr>
              <th scope="col">Métrica</th>
              <th scope="col" className="num">Medido</th>
              <th scope="col" className="num">Analítico</th>
              <th scope="col" className="num">Erro</th>
              {hasSim && <th scope="col" className="num">Simulação (IC)</th>}
              {hasSim && <th scope="col">Medido no IC?</th>}
              <th scope="col">Observação</th>
            </tr>
          </thead>
          <tbody>
            {METRIC_ROWS.map((name) => {
              const m = data.metrics[name];
              return (
                <tr key={name}>
                  <th scope="row">{name === "throughput" ? "Vazão X" : name === "W" ? "Tempo de resposta W" : name === "L" ? "Usuários no sistema L" : "Utilização ρ"}</th>
                  <td className="num">{formatMetric(name, m.measured, { precise: true })}</td>
                  <td className="num">{formatMetric(name, m.analytical, { precise: true })}</td>
                  <td className="num">{m.analytical_error_pct === null ? "—" : formatPercentNumber(m.analytical_error_pct)}</td>
                  {hasSim && (
                    <td className="num">
                      {m.simulated_mean === null ? "—" : formatMetric(name, m.simulated_mean, { precise: true, unit: false })}
                      {m.ci_low !== null && m.ci_high !== null && (
                        <span className="cell-sim">[{formatMetric(name, m.ci_low, { unit: false })}; {formatMetric(name, m.ci_high, { unit: false })}]</span>
                      )}
                    </td>
                  )}
                  {hasSim && <td>{m.measured_within_ci === null ? "—" : m.measured_within_ci ? "sim" : "não"}</td>}
                  <td>{ROLE[m.role]}{m.measured_derived ? "; medido derivado" : ""}</td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
      <p className="note">
        Erro = |modelo − medido| / medido. L (lei de Little) e ρ = X/(c·μ) são derivados das medições, não observados diretamente.
        {hasSim && " O IC é o da média simulada; um único teste medido tem variabilidade própria, então cair fora do IC não indica, sozinho, erro do modelo."}
      </p>
    </section>
  );
}

export function LevelsTable({ levels }: { levels: DatasetLevel[] }) {
  return (
    <div className="table-wrap">
      <table className="table">
        <caption className="sr-only">Níveis de carga importados</caption>
        <thead>
          <tr>
            <th scope="col" className="num">Usuários</th><th scope="col" className="num">Tempo médio</th>
            <th scope="col" className="num">p90</th><th scope="col" className="num">Vazão</th><th scope="col" className="num">Erros</th>
          </tr>
        </thead>
        <tbody>
          {levels.map((l) => (
            <tr key={l.users}>
              <td className="num">{l.users}</td>
              <td className="num">{ms(l.avg_ms)}</td>
              <td className="num">{l.p90_ms === null ? "—" : ms(l.p90_ms)}</td>
              <td className="num">{formatNumber(l.throughput)} req/s</td>
              <td className="num">{l.error_rate === null ? "—" : formatPercentNumber(l.error_rate * 100)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

/** Vários níveis de carga contra o M/M/c//N: gráfico e tabela. */
export function LevelsView({ data }: { data: LevelsCompareResponse }) {
  const colors = useThemeColors();
  const [metric, setMetric] = useState<LevelMetric>("W");
  const chart = useMemo(() => levelsChart(data.levels, metric, colors), [data, metric, colors]);
  const hasSim = data.simulation !== null;
  return (
    <section className="block" aria-label="Comparação por nível de carga">
      <h2 className="group-title">Medido × modelo {data.model}</h2>
      <ul className="rd-calibration">
        <li>μ = <strong>{formatNumber(Number(data.mu.toFixed(4)))} req/s</strong> ({MU_SOURCE_LABELS[data.mu_source].toLowerCase()}); {data.servers} servidor(es)</li>
        <li>Z = <strong>{formatNumber(Number(data.think_time.toFixed(4)))} s</strong> ({THINK_SOURCE[data.think_time_source]}){data.calibration_users !== null ? `; calibrado com ${data.calibration_users} usuário(s)` : ""}</li>
      </ul>
      <WarningList warnings={data.warnings} />
      <div className="exp-controls">
        <div className="field inline">
          <label htmlFor="rd-level-metric">Métrica</label>
          <select id="rd-level-metric" value={metric} onChange={(e) => setMetric(e.target.value as LevelMetric)}>
            {(Object.keys(LEVEL_METRIC_TITLE) as LevelMetric[]).map((k) => <option key={k} value={k}>{LEVEL_METRIC_TITLE[k]}</option>)}
          </select>
        </div>
      </div>
      <PlotlyChart data={chart.data} layout={chart.layout} label={`${LEVEL_METRIC_TITLE[metric]} por número de usuários`} />
      <div className="table-wrap">
        <table className="table">
          <caption className="sr-only">Medido e previsto por número de usuários</caption>
          <thead>
            <tr>
              <th scope="col" className="num">Usuários</th>
              <th scope="col" className="num">X medida</th><th scope="col" className="num">X modelo</th><th scope="col" className="num">Erro X</th>
              <th scope="col" className="num">W medido</th><th scope="col" className="num">W modelo</th><th scope="col" className="num">Erro W</th>
              {hasSim && <th scope="col" className="num">X simulada</th>}
              {hasSim && <th scope="col" className="num">W simulado</th>}
            </tr>
          </thead>
          <tbody>
            {data.levels.map((l) => (
              <tr key={l.users}>
                <td className="num">{l.users}</td>
                <td className="num">{formatMetric("throughput", l.throughput.measured, { unit: false })}</td>
                <td className="num">{formatMetric("throughput", l.throughput.analytical, { unit: false })}</td>
                <td className="num">{l.throughput.analytical_error_pct === null ? "—" : formatPercentNumber(l.throughput.analytical_error_pct)}</td>
                <td className="num">{formatMetric("W", l.W.measured, { unit: false })}</td>
                <td className="num">{formatMetric("W", l.W.analytical, { unit: false })}</td>
                <td className="num">{l.W.analytical_error_pct === null ? "—" : formatPercentNumber(l.W.analytical_error_pct)}</td>
                {hasSim && <td className="num">{l.throughput.simulated_mean === null ? "—" : formatMetric("throughput", l.throughput.simulated_mean, { unit: false })}</td>}
                {hasSim && <td className="num">{l.W.simulated_mean === null ? "—" : formatMetric("W", l.W.simulated_mean, { unit: false })}</td>}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <p className="note">Vazão em req/s e tempo de resposta em s. Erro = |modelo − medido| / medido.</p>
    </section>
  );
}

export function ReportButtons({ busy, onDownload }: { busy: boolean; onDownload: (format: "markdown" | "html") => void }) {
  return (
    <div className="rd-report" role="group" aria-label="Relatório experimental">
      <span>Relatório experimental:</span>
      <button type="button" className="btn btn-small" disabled={busy} onClick={() => onDownload("markdown")}>
        <IconDownload size={14} aria-hidden="true" /> Markdown (.md)
      </button>
      <button type="button" className="btn btn-small" disabled={busy} onClick={() => onDownload("html")}>
        <IconDownload size={14} aria-hidden="true" /> HTML
      </button>
    </div>
  );
}
