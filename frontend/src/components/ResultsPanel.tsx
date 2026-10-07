import { IconAlertCircle, IconChartDots3 } from "@tabler/icons-react";
import { useEffect, useState } from "react";
import type { ApiError } from "../api/client";
import type { RunnerState } from "../hooks/useRunner";
import { ChartsTab } from "./ChartsTab";
import { DetailsTab } from "./DetailsTab";
import { DeviationChart } from "./DeviationChart";
import { HeadlineCards } from "./HeadlineCards";
import { MetricsTable } from "./MetricsTable";
import { ReplicationsTab } from "./ReplicationsTab";
import { VerdictBanner } from "./VerdictBanner";

type TabKey = "results" | "charts" | "replications" | "details";
const TABS: { key: TabKey; label: string }[] = [
  { key: "results", label: "Resultados" },
  { key: "charts", label: "Gráficos" },
  { key: "replications", label: "Réplicas" },
  { key: "details", label: "Detalhes" },
];

const ACTION_VERB = { compare: "Comparando", simulate: "Simulando", calculate: "Calculando" } as const;

const ERROR_TITLES: Record<ApiError["code"], string> = {
  unstable_system: "Sistema instável",
  invalid_parameter: "Parâmetro inválido",
  invalid_request: "Requisição inválida",
  insufficient_sample: "Simulação curta demais",
  network: "Sem conexão com a API",
  http: "Erro na API",
  aborted: "Execução cancelada",
};

function EmptyState() {
  return (
    <div className="panel state">
      <IconChartDots3 size={32} aria-hidden="true" />
      <h2>Compare o analítico com a simulação</h2>
      <p>Escolha o modelo, ajuste os parâmetros e clique em Comparar. Você verá se a simulação concorda com o cálculo.</p>
    </div>
  );
}

function LoadingState({ action, startedAt, estimate }: { action: keyof typeof ACTION_VERB; startedAt: number; estimate: string | null }) {
  const [now, setNow] = useState(() => Date.now());
  useEffect(() => {
    const id = window.setInterval(() => setNow(Date.now()), 250);
    return () => window.clearInterval(id);
  }, []);
  const elapsed = Math.floor((now - startedAt) / 1000);
  return (
    <div className="panel state" role="status" aria-live="polite">
      <div className="spinner" aria-hidden="true" />
      <h2>{ACTION_VERB[action]}…</h2>
      <p>{elapsed} s{action !== "calculate" && estimate ? ` (${estimate})` : ""}</p>
    </div>
  );
}

function ErrorState({ error }: { error: ApiError }) {
  return (
    <div className="panel state state-error" role="alert">
      <IconAlertCircle size={32} aria-hidden="true" />
      <h2>{ERROR_TITLES[error.code]}</h2>
      <p>{error.message}</p>
      {error.code === "invalid_request" && <p>Corrija os campos destacados à esquerda.</p>}
      {error.code === "unstable_system" && (
        <p>Reduza λ, aumente μ ou o número de servidores. Com capacidade finita (K), o sistema é sempre estável.</p>
      )}
    </div>
  );
}

interface Props {
  state: RunnerState;
  estimate: string | null;
  onLoadRuns: () => void;
}

export function ResultsPanel({ state, estimate, onLoadRuns }: Props) {
  const [tab, setTab] = useState<TabKey>("results");

  // Cada nova execução volta para Resultados: o veredito é a primeira coisa a mostrar.
  useEffect(() => {
    if (state.status === "loading") setTab("results");
  }, [state.status]);

  if (state.status === "idle") return <EmptyState />;
  if (state.status === "loading") {
    return <LoadingState action={state.action} startedAt={state.startedAt} estimate={estimate} />;
  }
  if (state.status === "error") return <ErrorState error={state.error} />;

  const { result, runs } = state;
  return (
    <div className="panel results">
      <div role="tablist" aria-label="Seções do resultado" className="tabs">
        {TABS.map((t) => (
          <button
            key={t.key}
            role="tab"
            type="button"
            id={`tab-${t.key}`}
            aria-selected={tab === t.key}
            aria-controls={`panel-${t.key}`}
            className="tab"
            onClick={() => setTab(t.key)}
          >
            {t.label}
          </button>
        ))}
      </div>
      <div role="tabpanel" id={`panel-${tab}`} aria-labelledby={`tab-${tab}`} className="tab-panel">
        {tab === "results" && (
          <>
            <VerdictBanner result={result} />
            <HeadlineCards result={result} />
            {result.action === "compare" && <DeviationChart result={result} />}
            <MetricsTable result={result} />
          </>
        )}
        {tab === "charts" && <ChartsTab result={result} runsStatus={runs} onLoadRuns={onLoadRuns} />}
        {tab === "replications" && <ReplicationsTab result={result} runsStatus={runs} onLoadRuns={onLoadRuns} />}
        {tab === "details" && <DetailsTab result={result} />}
      </div>
    </div>
  );
}
