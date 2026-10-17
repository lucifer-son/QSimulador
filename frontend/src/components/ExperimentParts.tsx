import { IconAlertCircle, IconChartLine, IconPlayerPlay, IconPlayerStop } from "@tabler/icons-react";
import { useEffect, useState, type ReactNode } from "react";
import type { ApiError } from "../api/client";
import { MODELS } from "../domain/models";
import { VARIABLE_INFO, type SweepVariable, type SystemText } from "../domain/experiments";
import type { MetricName, MarkovModelKey } from "../domain/types";
import type { ExperimentState } from "../hooks/useExperiment";
import { metricTitle } from "./MetricsTable";
import { ERROR_TITLES } from "./ResultsPanel";

/** Parâmetros do Laboratório que o experimento mantém fixos (o que é varrido não aparece). */
export function FixedParameters({
  model, system, skip, title = "Parâmetros fixos",
}: { model: MarkovModelKey; system: SystemText; skip?: SweepVariable; title?: string }) {
  const info = MODELS[model];
  const items: [string, string][] = [["λ", system.lambda], ["μ", system.mu]];
  if (info.usesServers) items.push(["c", system.servers]);
  if (info.usesCapacity) items.push(["K", system.capacity]);
  const symbol: Record<string, SweepVariable> = { "λ": "lambda", "μ": "mu", c: "servers", K: "capacity" };
  return (
    <div className="fixed-params">
      <h2 className="group-title">{title}</h2>
      <p className="sub">{info.label}, com os valores do Laboratório.</p>
      <ul>
        {items.filter(([s]) => symbol[s] !== skip).map(([s, v]) => (
          <li key={s}><span>{s}</span><strong>{v || "—"}</strong></li>
        ))}
      </ul>
    </div>
  );
}

export function RunButtons({ busy, label, onCancel }: { busy: boolean; label: string; onCancel: () => void }) {
  return busy ? (
    <button type="button" className="btn btn-block" onClick={onCancel}>
      <IconPlayerStop size={16} aria-hidden="true" /> Cancelar
    </button>
  ) : (
    <button type="submit" className="btn btn-primary btn-block">
      <IconPlayerPlay size={16} aria-hidden="true" /> {label}
    </button>
  );
}

function Loading({ startedAt, what }: { startedAt: number; what: string }) {
  const [now, setNow] = useState(() => Date.now());
  useEffect(() => {
    const id = window.setInterval(() => setNow(Date.now()), 250);
    return () => window.clearInterval(id);
  }, []);
  return (
    <div className="panel state" role="status" aria-live="polite">
      <div className="spinner" aria-hidden="true" />
      <h2>{what}…</h2>
      <p>{Math.floor((now - startedAt) / 1000)} s</p>
    </div>
  );
}

interface ResultAreaProps<T> {
  state: ExperimentState<T>;
  idleTitle: string;
  idleText: string;
  loadingText: string;
  /** Títulos de erro que substituem os padrões (ex.: o CSV tem "amostras", não "simulação"). */
  errorTitles?: Partial<Record<ApiError["code"], string>>;
  children: (result: T) => ReactNode;
}

/** Os quatro estados do painel de resultados: vazio, executando, erro e resultado. */
export function ResultArea<T>({ state, idleTitle, idleText, loadingText, errorTitles, children }: ResultAreaProps<T>) {
  if (state.status === "idle") {
    return (
      <div className="panel state">
        <IconChartLine size={32} aria-hidden="true" />
        <h2>{idleTitle}</h2>
        <p>{idleText}</p>
      </div>
    );
  }
  if (state.status === "loading") return <Loading startedAt={state.startedAt} what={loadingText} />;
  if (state.status === "error") {
    return (
      <div className="panel state state-error" role="alert">
        <IconAlertCircle size={32} aria-hidden="true" />
        <h2>{errorTitles?.[state.error.code] ?? ERROR_TITLES[state.error.code]}</h2>
        <p>{state.error.message}</p>
        {state.error.code === "unstable_system" && (
          <p>O ponto de partida precisa ser estável: reduza λ, aumente μ ou o número de servidores no Laboratório.</p>
        )}
      </div>
    );
  }
  return <div className="panel results"><div className="tab-panel">{children(state.result)}</div></div>;
}

interface MetricSelectProps {
  id: string;
  model: MarkovModelKey;
  value: MetricName;
  available?: (name: MetricName) => boolean;
  onChange: (name: MetricName) => void;
}

export function MetricSelect({ id, model, value, available, onChange }: MetricSelectProps) {
  const names = MODELS[model].metrics.filter((n) => (available ? available(n) : true));
  return (
    <div className="field inline">
      <label htmlFor={id}>Métrica</label>
      <select id={id} value={value} onChange={(e) => onChange(e.target.value as MetricName)}>
        {names.map((n) => <option key={n} value={n}>{metricTitle(n)}</option>)}
      </select>
    </div>
  );
}

export const variableLabel = (v: SweepVariable): string => VARIABLE_INFO[v].label;
