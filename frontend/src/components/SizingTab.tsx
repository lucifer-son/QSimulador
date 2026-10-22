import { IconAlertTriangle, IconCheck, IconInfoCircle, IconX } from "@tabler/icons-react";
import { useEffect, useMemo, useRef, useState, type FormEvent } from "react";
import {
  runSizingCost, runSizingSla, runSizingTable,
  type SizingCostResponse, type SizingResponse, type SizingRow, type SizingSlaResponse, type SizingTableResponse,
} from "../api/sizing";
import { costChart, levelChart } from "../charts/sizing";
import { experimentFieldErrors, type ExpErrors, type SystemText } from "../domain/experiments";
import { formatInteger, formatMetric, formatNumber, formatPercentNumber } from "../domain/format";
import { MODELS } from "../domain/models";
import { experimentRecord } from "../domain/records";
import {
  buildSizingBody, COST_UNITS, familyNote, hasLoss, hasWaiting, INITIAL_SIZING, secondsIn,
  type CostUnit, type SizingAction, type SizingText,
} from "../domain/sizing";
import type { ExperimentModelKey } from "../domain/types";
import { useExperiment } from "../hooks/useExperiment";
import { useThemeColors } from "../hooks/useThemeColors";
import { ResultArea, RunButtons } from "./ExperimentParts";
import { PlotlyChart } from "./PlotlyChart";
import { SaveButton } from "./SaveButton";
import { TextField } from "./TextField";

const ACTION_LABEL: Record<SizingAction, string> = {
  table: "Tabela por servidores", sla: "Menor c pela meta", cost: "Custo mínimo",
};

interface Outcome {
  action: SizingAction;
  response: SizingResponse;
  costUnit: CostUnit;
}

interface Props {
  /** Modelo e valores do Laboratório: o dimensionamento parte do mesmo sistema. */
  model: ExperimentModelKey;
  system: SystemText;
  active: boolean;
}

/**
 * Fase 11: dimensionamento. Para uma faixa de servidores c, mostra as métricas, o nível de serviço P(Wq ≤ t),
 * o menor c que atinge a meta e o c de menor custo. Herda modelo e valores do Laboratório.
 */
export function SizingTab({ model, system, active }: Props) {
  const [text, setText] = useState<SizingText>(INITIAL_SIZING);
  const [errors, setErrors] = useState<ExpErrors>({});
  const { state, run, cancel } = useExperiment<Outcome>();
  const lastRequest = useRef<unknown>(null);   // o pedido que gerou o resultado, para o histórico

  useEffect(() => {
    if (state.status === "error") setErrors(experimentFieldErrors(state.error.fields, state.error.code));
  }, [state]);

  const edit = (field: keyof SizingText) => (value: string) => {
    setText((t) => ({ ...t, [field]: value }));
    setErrors(({ [field]: _gone, ...rest }) => rest);
  };

  const start = (action: SizingAction) => {
    const built = buildSizingBody(action, model, system, text);
    if (!built.ok) {
      setErrors(built.errors);
      return;
    }
    setErrors({});
    lastRequest.current = built.body;
    const call = { table: runSizingTable, sla: runSizingSla, cost: runSizingCost }[action];
    const costUnit = text.costUnit;
    void run(async (signal) => ({ action, response: await call(built.body, signal), costUnit }));
  };
  const submit = (e: FormEvent) => {
    e.preventDefault();
    start("table");
  };

  const waiting = hasWaiting(model);
  const note = familyNote(model);
  const info = MODELS[model];

  return (
    <div className="exp-grid" hidden={!active} role="tabpanel" id="sizing-panel" aria-label="Dimensionamento">
      <form className="panel params" aria-label="Parâmetros do dimensionamento" onSubmit={submit}>
        <p className="sub">
          Encontra quantos servidores atendem a uma meta e quanto custa cada escolha ({info.label}, com os valores do Laboratório).
        </p>
        {note && <p className="field-hint">{note}</p>}

        <h2 className="group-title">Faixa de servidores</h2>
        <div className="grid2">
          <TextField id="sizing-cmin" label="c inicial" value={text.cMin} error={errors.cMin} hint="Vazio: c − 1 do Laboratório" onChange={edit("cMin")} />
          <TextField id="sizing-cmax" label="c final" value={text.cMax} error={errors.cMax} hint="Vazio: c + 2 do Laboratório" onChange={edit("cMax")} />
        </div>

        <h2 className="group-title">{waiting ? "Nível de serviço" : "Bloqueio alvo"}</h2>
        {waiting ? (
          <div className="grid2">
            <TextField id="sizing-t" label="Tempo-limite t (s)" value={text.t} error={errors.t} hint="Mesma unidade de 1/μ" onChange={edit("t")} />
            <TextField id="sizing-target" label="Meta P(Wq ≤ t) (%)" value={text.target} error={errors.target} hint="Ex.: 80 para 80/20" onChange={edit("target")} />
          </div>
        ) : (
          <TextField id="sizing-blocking" label="Bloqueio máximo B (%)" value={text.blocking} error={errors.blocking} hint="Sem espera: a meta é o bloqueio" onChange={edit("blocking")} />
        )}

        <h2 className="group-title">Custos</h2>
        <div className="field">
          <label htmlFor="sizing-unit">Custos informados</label>
          <select id="sizing-unit" value={text.costUnit} onChange={(e) => edit("costUnit")(e.target.value)}>
            {COST_UNITS.map((u) => <option key={u.key} value={u.key}>{u.label}</option>)}
          </select>
        </div>
        <div className="grid2 spaced">
          <TextField id="sizing-hs" label="Servidor hₛ" value={text.serverCost} error={errors.serverCost} hint="Por servidor" onChange={edit("serverCost")} />
          {waiting && (
            <TextField id="sizing-he" label="Espera hₑ" value={text.waitCost} error={errors.waitCost} hint="Por cliente esperando" onChange={edit("waitCost")} />
          )}
          {hasLoss(model) && (
            <TextField
              id="sizing-hl" label="Perda h_perda" value={text.lossCost} error={errors.lossCost}
              hint={model === "erlangb" ? "Obrigatório (> 0) no Erlang-B" : "Opcional, por cliente perdido"} onChange={edit("lossCost")}
            />
          )}
        </div>

        <div className="actions spaced">
          <RunButtons busy={state.status === "loading"} label="Gerar tabela" onCancel={cancel} />
          {state.status !== "loading" && (
            <>
              <button type="button" className="btn btn-block" onClick={() => start("sla")}>Menor c pela meta</button>
              <button type="button" className="btn btn-block" onClick={() => start("cost")}>Custo mínimo</button>
            </>
          )}
        </div>
      </form>

      <ResultArea
        state={state}
        idleTitle="Dimensione o sistema"
        idleText="Gere a tabela por número de servidores, procure o menor c que atinge a meta ou o c de menor custo."
        loadingText="Calculando o dimensionamento"
        errorTitles={{ unstable_system: "Sistema instável" }}
      >
        {(outcome) => {
          const title = `Dimensionamento · ${ACTION_LABEL[outcome.action]} · ${info.label}`;
          return (
            <>
              <SaveButton
                suggestedTitle={title}
                build={(t) => experimentRecord("sizing", model, lastRequest.current, outcome.response, t ?? title, {
                  sizing_action: outcome.action, cost_unit: outcome.costUnit,
                })}
              />
              <SizingResultView action={outcome.action} result={outcome.response} costUnit={outcome.costUnit} />
            </>
          );
        }}
      </ResultArea>
    </div>
  );
}

const cell = (name: Parameters<typeof formatMetric>[0], value: number | null) =>
  value === null ? "—" : formatMetric(name, value, { unit: false });

/** O resultado do dimensionamento (também reaberto pelo Histórico). */
export function SizingResultView({
  action, result, costUnit,
}: { action: SizingAction; result: SizingResponse; costUnit: CostUnit }) {
  const colors = useThemeColors();
  const factor = secondsIn(costUnit);
  const unitLabel = COST_UNITS.find((u) => u.key === costUnit)!.label;
  const money = (value: number | null) =>
    value === null ? "—" : new Intl.NumberFormat("pt-BR", { minimumFractionDigits: 2, maximumFractionDigits: 2 }).format(value * factor);

  const rows = result.rows;
  const table = result as SizingTableResponse;
  const sla = result as SizingSlaResponse;
  const cost = result as SizingCostResponse;
  const best =
    action === "sla" ? sla.servers : action === "cost" ? cost.optimal_servers : (table.min_cost_servers ?? table.first_meeting_target);
  const goalPct = action === "sla" && sla.target !== null && sla.target !== undefined ? sla.target * 100 : null;

  const showBlock = result.family === "erlangb" || rows.some((r) => (r.p_block ?? 0) > 0);
  const showLevel = rows.some((r) => r.service_level !== null);
  const showMeet = rows.some((r) => r.meets_target !== null);
  const showCost = rows.some((r) => r.cost !== null);
  const showLoss = rows.some((r) => (r.loss_cost ?? 0) > 0);

  const level = useMemo(
    () => (showLevel ? levelChart(rows, goalPct, colors) : null), [rows, showLevel, goalPct, colors],
  );
  const costPlot = useMemo(
    () => (showCost ? costChart(rows, best ?? -1, factor, unitLabel, colors) : null), [rows, showCost, best, factor, unitLabel, colors],
  );

  const unstable = rows.filter((r) => r.status !== "ok");
  const headline = (() => {
    if (action === "sla") {
      const r = sla.row;
      return result.family === "erlangb"
        ? `Menor c que atinge o bloqueio alvo: ${sla.servers} servidores (B = ${formatPercentNumber((r.p_block ?? 0) * 100, 2)}).`
        : `Menor c que atinge a meta: ${sla.servers} servidores (P(Wq ≤ ${formatNumber(sla.t ?? 0)} s) = ${formatPercentNumber((r.service_level ?? 0) * 100, 1)}).`;
    }
    if (action === "cost") {
      return `c ótimo: ${cost.optimal_servers} servidores, com custo total de ${money(cost.optimal_cost)} (${unitLabel}).`;
    }
    const parts: string[] = [];
    if (table.first_meeting_target !== null && table.first_meeting_target !== undefined) parts.push(`menor c da tabela que atinge a meta: ${table.first_meeting_target}`);
    else if (showMeet) parts.push("nenhum c da tabela atinge a meta (amplie a faixa)");
    if (table.min_cost_servers !== null && table.min_cost_servers !== undefined) parts.push(`menor custo da tabela: c = ${table.min_cost_servers}`);
    return parts.length ? parts[0].charAt(0).toUpperCase() + parts.join("; ").slice(1) + "." : null;
  })();

  const rowClass = (r: SizingRow) =>
    r.status !== "ok" ? "row-bad" : r.servers === best ? "row-best" : undefined;

  return (
    <>
      {headline && (
        <div className="banner banner-success" role="status">
          <IconCheck size={18} aria-hidden="true" />
          <div>
            {headline}
            {action === "cost" && cost.at_boundary && (
              <div className="banner-detail">O ótimo caiu numa ponta da faixa pedida: o verdadeiro pode estar fora dela. Amplie a faixa.</div>
            )}
          </div>
        </div>
      )}
      {result.warnings.length > 0 && (
        <div className="banner banner-warning" role="status">
          <IconAlertTriangle size={18} aria-hidden="true" />
          <div>{result.warnings.map((w) => <div key={w}>{w}</div>)}</div>
        </div>
      )}
      {result.family !== result.model && (
        <div className="banner banner-info" role="note">
          <IconInfoCircle size={18} aria-hidden="true" />
          <div>
            {familyNote(result.model as ExperimentModelKey)}
          </div>
        </div>
      )}
      {unstable.length > 0 && (
        <p className="note">
          {unstable.length === 1 ? "1 linha" : `${unstable.length} linhas`} sem solução (instável ou fora do domínio): aparece destacada e nunca é escolhida.
        </p>
      )}

      {level && (
        <section className="block">
          <p className="sub">Nível de serviço por número de servidores (clientes atendidos em até t).</p>
          <PlotlyChart data={level.data} layout={level.layout} label="Nível de serviço por número de servidores" />
        </section>
      )}
      {costPlot && (
        <section className="block">
          <p className="sub">Custo total por número de servidores, com a parte de servidores, de espera{showLoss ? " e de perda" : ""}.</p>
          <PlotlyChart data={costPlot.data} layout={costPlot.layout} label="Custo por número de servidores" />
        </section>
      )}

      <div className="table-wrap">
        <table className="table">
          <caption className="sr-only">Métricas por número de servidores</caption>
          <thead>
            <tr>
              <th scope="col">c</th>
              <th scope="col">Situação</th>
              <th scope="col" className="num">ρ</th>
              <th scope="col" className="num">P(esperar)</th>
              <th scope="col" className="num">Lq</th>
              <th scope="col" className="num">Wq (s)</th>
              {showBlock && <th scope="col" className="num">Bloqueio</th>}
              {showLevel && <th scope="col" className="num">P(Wq ≤ t)</th>}
              {showMeet && <th scope="col">Meta</th>}
              {showCost && <th scope="col" className="num">Servidores</th>}
              {showCost && <th scope="col" className="num">Espera</th>}
              {showCost && showLoss && <th scope="col" className="num">Perda</th>}
              {showCost && <th scope="col" className="num">Custo total</th>}
            </tr>
          </thead>
          <tbody>
            {rows.map((r) => (
              <tr key={r.servers} className={rowClass(r)}>
                <th scope="row">{formatInteger(r.servers)}</th>
                <td>
                  {r.status === "ok" ? (
                    <span className="tag tag-ok"><IconCheck size={14} aria-hidden="true" />estável</span>
                  ) : (
                    <span className="tag tag-bad" title={r.message ?? undefined}>
                      <IconX size={14} aria-hidden="true" />{r.status === "unstable" ? "instável" : "inválido"}
                    </span>
                  )}
                </td>
                <td className="num">{cell("rho", r.rho)}</td>
                <td className="num">{cell("p_wait", r.p_wait)}</td>
                <td className="num">{cell("Lq", r.Lq)}</td>
                <td className="num">{cell("Wq", r.Wq)}</td>
                {showBlock && <td className="num">{cell("p_block", r.p_block)}</td>}
                {showLevel && <td className="num">{r.service_level === null ? "—" : formatPercentNumber(r.service_level * 100, 1)}</td>}
                {showMeet && (
                  <td>
                    {r.meets_target === null ? "—" : r.meets_target
                      ? <span className="tag tag-ok"><IconCheck size={14} aria-hidden="true" />atinge</span>
                      : <span className="tag tag-warn">não atinge</span>}
                  </td>
                )}
                {showCost && <td className="num">{money(r.server_cost)}</td>}
                {showCost && <td className="num">{money(r.wait_cost)}</td>}
                {showCost && showLoss && <td className="num">{money(r.loss_cost)}</td>}
                {showCost && <td className="num"><strong>{money(r.cost)}</strong></td>}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {showCost && <p className="note">Custos {unitLabel}: c·hₛ + λ·(1 − B)·Wq·hₑ{showLoss ? " + λ·B·h_perda" : ""}.</p>}
    </>
  );
}
