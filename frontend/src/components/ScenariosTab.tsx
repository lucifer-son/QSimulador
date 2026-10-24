import { IconAlertCircle, IconChartLine, IconDownload, IconPlus, IconTrash } from "@tabler/icons-react";
import { useEffect, useRef, useState, type FormEvent } from "react";
import { ApiError } from "../api/client";
import { exportScenariosCsv, type ScenariosResult } from "../api/scenarios";
import type { SimText, SystemText } from "../domain/experiments";
import { MODELS, LAB_MODEL_ORDER } from "../domain/models";
import { experimentRecord } from "../domain/records";
import {
  blankScenario, buildScenariosBody, estimateScenariosText, fieldKey, initialScenarios, MAX_SCENARIOS,
  scenarioFieldErrors, VARIABLE_LABEL, visibleVariables, type ScenarioText, type VariableKey,
} from "../domain/scenarios";
import type { ExperimentModelKey } from "../domain/types";
import { useScenarioRun } from "../hooks/useScenarioRun";
import { FixedParameters, RunButtons } from "./ExperimentParts";
import { ERROR_TITLES } from "./ResultsPanel";
import { SaveButton } from "./SaveButton";
import { ScenariosView } from "./ScenariosView";
import { TextField } from "./TextField";

interface Props {
  /** Modelo, valores e simulação do Laboratório: a base da comparação e as configurações de cada réplica. */
  model: ExperimentModelKey;
  system: SystemText;
  sim: SimText;
  active: boolean;
}

const HINT: Record<VariableKey, string> = {
  lambda: "12 ou +20%", mu: "2 ou −10%", servers: "12 ou +1", capacity: "20 ou +5", cv: "1,5 ou +50%", k: "4 ou +1",
};

function downloadBlob(blob: Blob, filename: string) {
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = filename;
  document.body.appendChild(link);
  link.click();
  link.remove();
  URL.revokeObjectURL(url);
}

/**
 * Fase 12: compara a base (o sistema do Laboratório) com até 10 cenários, cada um com alguns valores trocados.
 * As réplicas usam as mesmas sementes em todos os cenários, então a diferença é pareada e o IC dela é mais justo.
 */
export function ScenariosTab({ model, system, sim, active }: Props) {
  const [scenarios, setScenarios] = useState<ScenarioText[]>(() => initialScenarios(model));
  const nextId = useRef(3);
  const [bonferroni, setBonferroni] = useState(false);
  const [errors, setErrors] = useState<Record<string, string>>({});
  const { state, run, cancel } = useScenarioRun();
  const lastRequest = useRef<Record<string, unknown> | null>(null);
  const [csv, setCsv] = useState<{ busy: boolean; error: string | null }>({ busy: false, error: null });

  useEffect(() => {
    if (state.status === "error") setErrors(scenarioFieldErrors(state.error.fields, state.error.code, scenarios).fields);
    // Só reage ao erro novo; editar a lista não deve reabrir os erros antigos.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [state]);

  const clearError = (key: string) => setErrors(({ [key]: _gone, ...rest }) => rest);
  const edit = (id: number, field: keyof ScenarioText, value: string) => {
    setScenarios((list) => list.map((s) => (s.id === id ? { ...s, [field]: value } : s)));
    clearError(fieldKey(id, field as VariableKey));
  };
  const add = () => {
    if (scenarios.length >= MAX_SCENARIOS) return;
    setScenarios((list) => [...list, blankScenario(nextId.current++)]);
  };
  const remove = (id: number) => setScenarios((list) => list.filter((s) => s.id !== id));

  const start = (e: FormEvent) => {
    e.preventDefault();
    const built = buildScenariosBody(model, system, sim, scenarios, bonferroni);
    if (!built.ok) {
      setErrors(built.errors);
      return;
    }
    setErrors({});
    setCsv({ busy: false, error: null });
    lastRequest.current = built.body;
    void run(built.body);
  };

  const exportCsv = async (result: ScenariosResult) => {
    setCsv({ busy: true, error: null });
    try {
      // A semente que a API usou vai junto, senão um pedido sem semente geraria outra comparação.
      const blob = await exportScenariosCsv({ ...lastRequest.current, seed: result.settings.seed });
      downloadBlob(blob, "cenarios.csv");
      setCsv({ busy: false, error: null });
    } catch (e) {
      setCsv({ busy: false, error: e instanceof ApiError ? e.message : "Não foi possível exportar o CSV." });
    }
  };

  const info = MODELS[model];
  const estimate = estimateScenariosText(system, scenarios, sim);
  const busy = state.status === "loading";

  return (
    <div className="exp-grid" hidden={!active} role="tabpanel" id="scenarios-panel" aria-label="Cenários">
      <form className="panel params" aria-label="Parâmetros da comparação de cenários" onSubmit={start}>
        <p className="sub">
          Compara a base ({info.label}, com os valores e a simulação do Laboratório) com até {MAX_SCENARIOS} cenários que
          trocam alguns valores. Em cada campo, digite o valor ou a variação (+20%, +1).
        </p>
        <FixedParameters model={model} system={system} title="Base" />

        <h2 className="group-title">Cenários</h2>
        {scenarios.map((s, index) => (
          <fieldset key={s.id} className="scenario-card" aria-label={`Cenário ${index + 1}`}>
            <legend>Cenário {index + 1}</legend>
            <TextField
              id={`scn-${s.id}-name`} label="Nome" value={s.name} error={errors[fieldKey(s.id, "name")]}
              onChange={(v) => edit(s.id, "name", v)}
            />
            <div className="field">
              <label htmlFor={`scn-${s.id}-model`}>Modelo</label>
              <select id={`scn-${s.id}-model`} value={s.model} onChange={(e) => edit(s.id, "model", e.target.value)}>
                <option value="">Igual à base ({info.label})</option>
                {LAB_MODEL_ORDER.filter((k) => k !== model).map((k) => <option key={k} value={k}>{MODELS[k].label}</option>)}
              </select>
              {errors[fieldKey(s.id, "model")] && <span className="field-error" role="alert">{errors[fieldKey(s.id, "model")]}</span>}
            </div>
            <div className="grid2">
              {visibleVariables(model, s).map((v) => (
                <TextField
                  key={v} id={`scn-${s.id}-${v}`} label={VARIABLE_LABEL[v]} value={s[v]}
                  error={errors[fieldKey(s.id, v)]} hint={HINT[v]} onChange={(value) => edit(s.id, v, value)}
                />
              ))}
            </div>
            {errors[fieldKey(s.id, "service")] && <span className="field-error" role="alert">{errors[fieldKey(s.id, "service")]}</span>}
            <button type="button" className="btn btn-small" onClick={() => remove(s.id)} aria-label={`Remover cenário ${index + 1}`}>
              <IconTrash size={14} aria-hidden="true" /> Remover
            </button>
          </fieldset>
        ))}
        {errors.scenarios && <span className="field-error" role="alert">{errors.scenarios}</span>}
        <button type="button" className="btn btn-block" onClick={add} disabled={scenarios.length >= MAX_SCENARIOS}>
          <IconPlus size={16} aria-hidden="true" /> Adicionar cenário
        </button>

        <h2 className="group-title">Simulação</h2>
        <p className="field-hint">
          T = {sim.simulationTime} s, {sim.replications} réplicas, warm-up {sim.warmupTime} s, semente {sim.seed || "aleatória"} (do Laboratório).
        </p>
        {(["simulationTime", "replications", "warmupTime", "seed"] as const).map((k) => errors[k] && (
          <span key={k} className="field-error" role="alert">{errors[k]}</span>
        ))}
        <label className="check">
          <input type="checkbox" checked={bonferroni} onChange={(e) => setBonferroni(e.target.checked)} />
          Correção de Bonferroni nos ICs das diferenças
        </label>
        {estimate && <p className="field-hint">Estimativa: {estimate}.</p>}

        <div className="actions spaced">
          <RunButtons busy={busy} label="Executar todos" onCancel={cancel} />
        </div>
      </form>

      {state.status === "idle" && (
        <div className="panel state">
          <IconChartLine size={32} aria-hidden="true" />
          <h2>Compare cenários</h2>
          <p>Monte os cenários e execute: cada um é simulado com as mesmas sementes da base, e a diferença sai com intervalo de confiança.</p>
        </div>
      )}
      {state.status === "loading" && (
        <div className="panel results">
          <div className="tab-panel">
            <p role="status" aria-live="polite" className="sub">Comparando os cenários…</p>
            {state.partial && (
              <ScenariosView data={state.partial} progress={{ completed: state.completed, total: state.total }} />
            )}
          </div>
        </div>
      )}
      {state.status === "error" && (
        <div className="panel state state-error" role="alert">
          <IconAlertCircle size={32} aria-hidden="true" />
          <h2>{ERROR_TITLES[state.error.code]}</h2>
          <p>{state.error.message}</p>
          {state.error.code === "unstable_system" && (
            <p>A base precisa ser estável: reduza λ, aumente μ ou o número de servidores no Laboratório.</p>
          )}
          {Object.keys(errors).length > 0 && <p>Corrija os campos destacados à esquerda.</p>}
        </div>
      )}
      {state.status === "success" && (
        <div className="panel results">
          <div className="tab-panel">
            <div className="save-row">
              <SaveButton
                suggestedTitle={`Cenários · ${info.label}`}
                build={(t) => experimentRecord(
                  "scenarios", model, { ...lastRequest.current, seed: state.result.settings.seed }, state.result,
                  t ?? `Cenários · ${info.label}`,
                )}
              />
              <button type="button" className="btn btn-small" disabled={csv.busy} onClick={() => void exportCsv(state.result)}>
                <IconDownload size={15} aria-hidden="true" /> {csv.busy ? "Exportando…" : "Exportar CSV"}
              </button>
              {csv.error && <span className="field-error" role="alert">{csv.error}</span>}
            </div>
            <ScenariosView data={state.result} />
          </div>
        </div>
      )}
    </div>
  );
}
