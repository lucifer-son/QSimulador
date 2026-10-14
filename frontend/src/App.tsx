import { IconChartDots3 } from "@tabler/icons-react";
import { useEffect, useState } from "react";
import { fieldErrorsFromApi } from "./api/fieldErrors";
import { ParametersPanel } from "./components/ParametersPanel";
import { ResultsPanel } from "./components/ResultsPanel";
import { ExperimentTab } from "./components/ExperimentTab";
import { RealDataTab } from "./components/RealDataTab";
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
type Theme = "light" | "dark";

function initialTheme(): Theme {
  return window.localStorage.getItem("qsimulador-theme") === "dark" ? "dark" : "light";
}

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
  const [theme, setTheme] = useState<Theme>(initialTheme);
  
  const [activeTab, setActiveTab] = useState<"laboratorio" | "experimentos" | "dados">("laboratorio");
  // Os experimentos só são montados na primeira visita; depois ficam montados para manter os resultados.
  const [experimentsOpened, setExperimentsOpened] = useState(false);
  const [realDataOpened, setRealDataOpened] = useState(false);

  const { state, run, cancel, loadRuns } = useRunner();

  useEffect(() => {
    document.documentElement.dataset.theme = theme;
    document.documentElement.style.colorScheme = theme;
    window.localStorage.setItem("qsimulador-theme", theme);
  }, [theme]);

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
          <button
            type="button"
            className="nav-item"
            aria-current={activeTab === "laboratorio" ? "page" : undefined}
            onClick={() => setActiveTab("laboratorio")}
          >
            Laboratório
          </button>
          <button
            type="button"
            className="nav-item"
            aria-current={activeTab === "experimentos" ? "page" : undefined}
            onClick={() => { setActiveTab("experimentos"); setExperimentsOpened(true); }}
          >
            Experimentos
          </button>
          <button
            type="button"
            className="nav-item"
            aria-current={activeTab === "dados" ? "page" : undefined}
            onClick={() => { setActiveTab("dados"); setRealDataOpened(true); }}
          >
            Dados reais
          </button>
          <button
            type="button"
            className="nav-item theme-toggle"
            aria-pressed={theme === "dark"}
            aria-label={`Ativar tema ${theme === "dark" ? "claro" : "escuro"}`}
            onClick={() => setTheme((current) => current === "dark" ? "light" : "dark")}
          >
            {theme === "dark" ? "☀ Tema claro" : "☾ Tema escuro"}
          </button>
        </nav>
      </header>
      
      <main className="layout" hidden={activeTab !== "laboratorio"}>
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

      {experimentsOpened && (
        <main className="layout layout-wide" hidden={activeTab !== "experimentos"}>
          <ExperimentTab model={model} system={systems[model]} sim={sim} />
        </main>
      )}

      {realDataOpened && (
        <main className="layout layout-wide" hidden={activeTab !== "dados"}>
          <RealDataTab />
        </main>
      )}
    </div>
  );
}
