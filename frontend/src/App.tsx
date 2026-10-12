import { IconChartDots3 } from "@tabler/icons-react";
import { useEffect, useState } from "react";
import { fieldErrorsFromApi } from "./api/fieldErrors";
import { ParametersPanel } from "./components/ParametersPanel";
import { ResultsPanel } from "./components/ResultsPanel";
import { ExperimentTab } from "./components/ExperimentTab"; // Importámos a nossa nova aba!
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
  
  // O nosso "interruptor" para mudar de ecrã
  const [activeTab, setActiveTab] = useState<"laboratorio" | "experimentos">("laboratorio");
  
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
        <h1 className="brand"><IconChartDots3 size={22} aria-hidden="true" />QSimulador</h1>
        <nav aria-label="Seções">
          <span 
            className="nav-item" 
            aria-current={activeTab === "laboratorio" ? "page" : undefined}
            onClick={() => setActiveTab("laboratorio")}
            style={{ cursor: "pointer" }}
          >
            Laboratório
          </span>
          
          <span 
            className="nav-item" 
            aria-current={activeTab === "experimentos" ? "page" : undefined}
            onClick={() => setActiveTab("experimentos")}
            style={{ cursor: "pointer" }}
          >
            Experimentos
          </span>
          
          <span className="nav-item soon" aria-disabled="true">Dados reais <small>em breve</small></span>
        </nav>
      </header>
      
      <main className="layout" style={{ display: activeTab === "experimentos" ? "block" : undefined }}>
        {activeTab === "laboratorio" ? (
          <>
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
          </>
        ) : (
          <div style={{ backgroundColor: "#1e1e1e", borderRadius: "8px", border: "1px solid #333", minHeight: "80vh" }}>
            <ExperimentTab 
              currentModel={model} 
              baseParams={{
                lambda: Number(values.lambda) || 0,
                mu: Number(values.mu) || 0,
                servers: Number(values.servers) || 1,
                capacity: Number(values.capacity) || 1
              }}
            />
          </div>
        )}
      </main>
    </div>
  );
}