import { IconChartDots3 } from "@tabler/icons-react";
import { useEffect, useState } from "react";
import { fieldErrorsFromApi } from "./api/fieldErrors";
import { ParametersPanel } from "./components/ParametersPanel";
import { ResultsPanel } from "./components/ResultsPanel";
import { estimateText } from "./domain/estimate";
import { MODEL_ORDER, MODELS } from "./domain/models";
import { parseForm } from "./domain/request";
import {
  SYSTEM_FIELDS, type Action, type FieldErrors, type FieldKey, type FormValues, type ModelKey,
} from "./domain/types";
import { useRunner } from "./hooks/useRunner";

type SystemValues = Pick<FormValues, "lambda" | "mu" | "servers" | "capacity">;
type SimValues = Pick<FormValues, "simulationTime" | "replications" | "warmupTime" | "seed">;

const INITIAL_SIM: SimValues = { simulationTime: "2000", replications: "10", warmupTime: "100", seed: "2026" };

/** Cada modelo guarda os próprios valores: trocar de modelo não apaga o que foi digitado. */
function initialSystems(): Record<ModelKey, SystemValues> {
  return Object.fromEntries(MODEL_ORDER.map((k) => [k, { ...MODELS[k].example }])) as Record<ModelKey, SystemValues>;
}

export default function App() {
  const [model, setModel] = useState<ModelKey>("mmck");
  const [systems, setSystems] = useState(initialSystems);
  const [sim, setSim] = useState<SimValues>(INITIAL_SIM);
  const [localErrors, setLocalErrors] = useState<FieldErrors>({});
  const [apiErrors, setApiErrors] = useState<FieldErrors>({});
  const { state, run, cancel, loadRuns } = useRunner();

  useEffect(() => {
    setApiErrors(state.status === "error" ? fieldErrorsFromApi(state.error) : {});
  }, [state]);

  const values: FormValues = { ...systems[model], ...sim };
  const errors: FieldErrors = { ...apiErrors, ...localErrors };
  const estimate = estimateText(values.lambda, values.simulationTime, values.replications);

  const clearError = (field: FieldKey) => {
    setLocalErrors(({ [field]: _l, ...rest }) => rest);
    setApiErrors(({ [field]: _a, ...rest }) => rest);
  };

  const handleChange = (field: FieldKey, value: string) => {
    clearError(field);
    if (SYSTEM_FIELDS.includes(field)) {
      setSystems((prev) => ({ ...prev, [model]: { ...prev[model], [field]: value } }));
    } else {
      setSim((prev) => ({ ...prev, [field]: value }));
    }
  };

  const handleModelChange = (next: ModelKey) => {
    setModel(next);
    setLocalErrors({});
    setApiErrors({});
  };

  const handleRun = (action: Action) => {
    const parsed = parseForm(values, model, action);
    if (!parsed.ok) {
      setLocalErrors(parsed.errors);
      return;
    }
    setLocalErrors({});
    void run(model, action, parsed.params);
  };

  return (
    <div className="app">
      <header className="topbar">
        <div className="brand"><IconChartDots3 size={22} aria-hidden="true" />QSimulador</div>
        <nav aria-label="Seções">
          <span className="nav-item" aria-current="page">Laboratório</span>
          <span className="nav-item soon" aria-disabled="true">Experimentos <small>em breve</small></span>
          <span className="nav-item soon" aria-disabled="true">Dados reais <small>em breve</small></span>
        </nav>
      </header>
      <main className="layout">
        <ParametersPanel
          model={model}
          values={values}
          errors={errors}
          estimate={estimate}
          busy={state.status === "loading"}
          onModelChange={handleModelChange}
          onChange={handleChange}
          onRun={handleRun}
          onCancel={cancel}
        />
        <ResultsPanel state={state} estimate={estimate} onLoadRuns={() => void loadRuns()} />
      </main>
    </div>
  );
}
