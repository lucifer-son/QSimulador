import { IconAlertTriangle, IconCircleCheck, IconInfoCircle } from "@tabler/icons-react";
import type {
  AnalysisResponse, Diagnostic, Estimates, Level, RankingItem,
} from "../api/realdata";
import type { SimulatedLevelComparison } from "../api/realdataExtra";
import {
  bannerTone, CONFIDENCE_LABEL, CRITERIA_LABEL, CRITERIA_ORDER, DIAGNOSTIC_LABEL,
} from "../domain/realdata";
import { formatInteger, formatMetric, formatNumber, formatPercentNumber } from "../domain/format";
import { METRIC_INFO } from "../domain/metrics";
import type { MetricName } from "../domain/types";

const ICONS = { success: IconCircleCheck, warning: IconAlertTriangle, info: IconInfoCircle };

export function RecommendationBanner({ result }: { result: AnalysisResponse }) {
  const tone = bannerTone(result);
  const Icon = ICONS[tone];
  const pick = result.recommended ?? result.nearest;
  const title = result.status === "recommended" && pick
    ? `Modelo recomendado: ${pick.notation}. Confiança ${CONFIDENCE_LABEL[result.confidence]}.`
    : pick
      ? `Nenhum modelo do catálogo se ajusta bem. O mais próximo é ${pick.notation}. Confiança ${CONFIDENCE_LABEL[result.confidence]}.`
      : "Nenhum modelo do catálogo é compatível com estes dados.";
  return (
    <div className={`banner banner-${tone}`} role="status">
      <Icon size={20} aria-hidden="true" />
      <div>
        <div>{title}</div>
        <div className="banner-detail">{result.rationale}</div>
      </div>
    </div>
  );
}

export function WarningList({ warnings, estimates }: { warnings: string[]; estimates: Estimates }) {
  const items = [...warnings];
  if (estimates.autoconsistent) {
    items.push(
      "μ não pôde ser estimado de forma independente (há um único nível de carga). O tempo de resposta previsto coincide com o medido " +
      "por construção e não valida o modelo. Informe o tempo de serviço ou rode o teste com mais de um nível de usuários para aumentar a confiança.",
    );
  }
  if (items.length === 0) return null;
  return (
    <div className="block">
      <h3 className="group-title">Avisos</h3>
      <ul className="notes">{items.map((w) => <li key={w}>{w}</li>)}</ul>
    </div>
  );
}

const SOURCE: Record<string, string> = {
  informado: "informado", estimado: "estimado", assumido: "assumido", menor_nivel: "menor nível de carga",
  autoconsistente: "calibrado pelo tempo de resposta",
};

export function EstimatesList({ estimates }: { estimates: Estimates }) {
  const items: [string, string][] = [
    ["μ", estimates.mu === null ? `— (${SOURCE[estimates.mu_source]})` : `${formatNumber(estimates.mu)} req/s (${SOURCE[estimates.mu_source]})`],
    ["c", `${estimates.servers} (${SOURCE[estimates.servers_source]})`],
  ];
  if (estimates.think_time != null) items.push(["Z", `${formatNumber(estimates.think_time)} s (${SOURCE[estimates.think_source ?? "estimado"]})`]);
  if (estimates.capacity) items.push(["K", `${estimates.capacity} (${SOURCE[estimates.capacity_source ?? "estimado"]})`]);
  return (
    <div className="block fixed-params">
      <h3 className="group-title">Parâmetros estimados</h3>
      <ul>{items.map(([s, v]) => <li key={s}><span>{s}</span><strong>{v}</strong></li>)}</ul>
      {estimates.notes.map((n) => <p className="note" key={n}>{n}</p>)}
    </div>
  );
}

const DIAG_TAG: Record<Diagnostic["status"], string> = {
  ok: "tag tag-ok", atencao: "tag tag-warn", critico: "tag tag-bad", info: "tag tag-info",
};

export function DiagnosticList({ diagnostics }: { diagnostics: Diagnostic[] }) {
  return (
    <div className="block">
      <h3 className="group-title">Verificação dos dados</h3>
      <ul className="diag">
        {diagnostics.map((d) => (
          <li key={d.id}>
            <span className={DIAG_TAG[d.status]}>{DIAGNOSTIC_LABEL[d.status]}</span>
            <div><strong>{d.title}</strong><span className="diag-evidence">{d.evidence}</span></div>
          </li>
        ))}
      </ul>
    </div>
  );
}

/** Matriz critério × modelo: mostra por que cada modelo ganhou ou perdeu, fator por fator. */
export function CriteriaTable({ ranking }: { ranking: RankingItem[] }) {
  const columns = CRITERIA_ORDER.filter((id) => ranking.some((r) => r.criteria.some((c) => c.id === id)));
  return (
    <div className="block">
      <h3 className="group-title">Modelos avaliados, critério por critério</h3>
      <p className="sub">
        Um modelo só concorre se atender aos critérios estruturais. Entre os que concorrem, vale o menor escore
        (erro nas métricas de validação + penalidade por parâmetro estimado); em empate, o mais simples.
      </p>
      <div className="table-wrap">
        <table className="table criteria">
          <caption className="sr-only">Critérios atendidos por cada modelo candidato</caption>
          <thead>
            <tr>
              <th scope="col">Modelo</th>
              {columns.map((id) => <th scope="col" key={id}>{CRITERIA_LABEL[id]}</th>)}
              <th scope="col" className="num">Erro</th>
              <th scope="col" className="num">Parcimônia</th>
              <th scope="col" className="num">Escore</th>
              <th scope="col">Observação</th>
            </tr>
          </thead>
          <tbody>
            {ranking.map((r) => {
              const failed = r.criteria.find((c) => !c.passed);
              return (
                <tr key={r.key} className={r.recommended ? "row-picked" : undefined}>
                  <th scope="row">
                    {r.notation} {r.recommended && <span className="tag tag-ok">Recomendado</span>}
                  </th>
                  {columns.map((id) => {
                    const c = r.criteria.find((x) => x.id === id);
                    if (!c) return <td key={id}>—</td>;
                    return (
                      <td key={id} title={c.reason}>
                        <span className={c.passed ? "tag tag-ok" : "tag tag-bad"}>
                          <span aria-hidden="true">{c.passed ? "✓" : "✗"}</span>
                          <span className="sr-only">{c.passed ? "atende" : "não atende"}</span>
                        </span>
                      </td>
                    );
                  })}
                  <td className="num">{r.error_pct == null ? "—" : formatPercentNumber(r.error_pct, 1)}</td>
                  <td className="num">{r.score_pct == null ? "—" : `+${formatNumber(r.penalty_pp)} p.p.`}</td>
                  <td className="num">{r.score_pct == null ? "—" : formatPercentNumber(r.score_pct, 1)}</td>
                  <td className="cell-reason">{failed ? failed.reason : r.recommended ? "Melhor ajuste dentro do catálogo." : ""}</td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </div>
  );
}

export function LevelsTable({ levels }: { levels: Level[] }) {
  return (
    <div className="block">
      <h3 className="group-title">Métricas medidas</h3>
      <div className="table-wrap">
        <table className="table">
          <caption className="sr-only">Métricas medidas em cada nível de carga</caption>
          <thead>
            <tr>
              <th scope="col">Usuários</th>
              <th scope="col" className="num">Amostras</th>
              <th scope="col" className="num">λ̂ (req/s)</th>
              <th scope="col" className="num">X̂ (req/s)</th>
              <th scope="col" className="num">W̄ (s)</th>
              <th scope="col" className="num">p90 (s)</th>
              <th scope="col" className="num">Rejeições</th>
            </tr>
          </thead>
          <tbody>
            {levels.map((l, i) => (
              <tr key={l.users ?? `janela-${i}`}>
                <th scope="row">{l.users ?? "janela inteira"}</th>
                <td className="num">{formatInteger(l.metrics.samples)}</td>
                <td className="num">{formatNumber(l.metrics.arrival_rate)}</td>
                <td className="num">{formatNumber(l.metrics.throughput)}</td>
                <td className="num">{formatNumber(l.metrics.mean_response)}</td>
                <td className="num">{l.metrics.p90 == null ? "—" : formatNumber(l.metrics.p90)}</td>
                <td className="num">{formatPercentNumber(l.metrics.p_block * 100)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

const COMPARED: MetricName[] = ["W", "throughput", "L", "p_block"];

export function ComparisonTable({ comparison }: { comparison: SimulatedLevelComparison[] }) {
  const rows = comparison.flatMap((lv, i) =>
    COMPARED.filter((name) => name in lv.metrics).map((name) => ({ lv, i, name, m: lv.metrics[name] })),
  );
  const hasSim = rows.some((r) => r.m.simulated_mean != null);
  return (
    <div className="table-wrap">
      <table className="table">
        <caption className="sr-only">Modelo comparado com a medição, por nível de carga</caption>
        <thead>
          <tr>
            <th scope="col">Usuários</th>
            <th scope="col">Métrica</th>
            <th scope="col" className="num">Modelo</th>
            <th scope="col" className="num">Medido</th>
            <th scope="col" className="num">IC do medido</th>
            <th scope="col" className="num">Erro relativo</th>
            <th scope="col">Modelo dentro do IC</th>
            {hasSim && <th scope="col" className="num">Simulação (IC)</th>}
            {hasSim && <th scope="col" className="num">Erro da simulação</th>}
            {hasSim && <th scope="col">Simulação no IC do medido</th>}
          </tr>
        </thead>
        <tbody>
          {rows.map(({ lv, i, name, m }) => (
            <tr key={`${i}-${name}`}>
              <th scope="row">{lv.users ?? "janela"}</th>
              <td title={METRIC_INFO[name].label}>{METRIC_INFO[name].short}</td>
              <td className="num">{formatMetric(name, m.model, { precise: true })}</td>
              <td className="num">{formatMetric(name, m.observed, { precise: true })}</td>
              <td className="num">
                {m.observed_ci_low == null || m.observed_ci_high == null
                  ? "—"
                  : `${formatMetric(name, m.observed_ci_low, { unit: false })} a ${formatMetric(name, m.observed_ci_high)}`}
              </td>
              <td className="num">{m.relative_error_pct == null ? "—" : formatPercentNumber(m.relative_error_pct, 1)}</td>
              <td>
                {m.model_within_observed_ci == null ? "—" : (
                  <span className={m.model_within_observed_ci ? "tag tag-ok" : "tag tag-bad"}>
                    {m.model_within_observed_ci ? "Sim" : "Não"}
                  </span>
                )}
              </td>
              {hasSim && (
                <td className="num">
                  {m.simulated_mean == null ? "—" : formatMetric(name, m.simulated_mean, { precise: true, unit: false })}
                  {m.simulated_ci_low != null && m.simulated_ci_high != null && (
                    <span className="cell-sim"> [{formatMetric(name, m.simulated_ci_low, { unit: false })}; {formatMetric(name, m.simulated_ci_high, { unit: false })}]</span>
                  )}
                </td>
              )}
              {hasSim && <td className="num">{m.simulated_error_pct == null ? "—" : formatPercentNumber(m.simulated_error_pct, 1)}</td>}
              {hasSim && (
                <td>
                  {m.simulation_within_observed_ci == null ? "—" : (
                    <span className={m.simulation_within_observed_ci ? "tag tag-ok" : "tag tag-bad"}>
                      {m.simulation_within_observed_ci ? "Sim" : "Não"}
                    </span>
                  )}
                </td>
              )}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
