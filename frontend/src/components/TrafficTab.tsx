import { IconAlertCircle, IconChartLine, IconDownload, IconPlus } from "@tabler/icons-react";
import { useCallback, useEffect, useRef, useState, type FormEvent, type ReactNode } from "react";
import { ApiError } from "../api/client";
import {
  estimateVideo, exportTrafficCsv, simulateTraffic, streamTraffic, validateVideo,
  type ApproachKey, type CompareResult, type PlanRow, type SweepPoint, type SweepResult, type TrafficCsvPath,
  type TrafficResult, type VideoEstimate, type VideoValidation,
} from "../api/traffic";
import { trafficRecord, TRAFFIC_TITLE, type TrafficSnapshot } from "../domain/records";
import {
  applyEstimate, blankPlan, blankSweep, blankTraffic, buildComparisonBody, buildSweepBody, buildTrafficBody, exampleTraffic,
  trafficErrors, type Built, type PlanText, type SweepText, type TrafficErrors, type TrafficText,
} from "../domain/traffic";
import { useExperiment, type ExperimentState } from "../hooks/useExperiment";
import { useTrafficStream, type StreamProgress } from "../hooks/useTrafficStream";
import { ResultArea, RunButtons } from "./ExperimentParts";
import { ERROR_TITLES } from "./ResultsPanel";
import { SaveButton } from "./SaveButton";
import { TrafficForm } from "./TrafficForm";
import { PlansPanel, SweepPanel } from "./TrafficPanels";
import {
  blankVideoFiles, blankVideoParams, videoForm, VideoEstimateView, VideoPanel, type VideoFiles, type VideoParams,
} from "./TrafficVideo";
import { Progress, TrafficCompareView, TrafficSimulationView, TrafficSweepView, TrafficValidationView } from "./TrafficViews";

type Mode = "simulate" | "compare" | "sweep" | "video";
const MODES: { key: Mode; label: string }[] = [
  { key: "simulate", label: "Simular" },
  { key: "compare", label: "Comparar planos" },
  { key: "sweep", label: "Varrer o verde" },
  { key: "video", label: "Dados do vídeo" },
];
const CSV_PATH: Record<"simulate" | "compare" | "sweep", { path: TrafficCsvPath; file: string }> = {
  simulate: { path: "/api/traffic/export.csv", file: "cruzamento.csv" },
  compare: { path: "/api/traffic/compare/export.csv", file: "cruzamento-planos.csv" },
  sweep: { path: "/api/traffic/sweep/export.csv", file: "cruzamento-varredura.csv" },
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

function ErrorPanel({ error, hasFieldErrors }: { error: ApiError; hasFieldErrors: boolean }) {
  return (
    <div className="panel state state-error" role="alert">
      <IconAlertCircle size={32} aria-hidden="true" />
      <h2>{ERROR_TITLES[error.code]}</h2>
      <p>{error.message}</p>
      {hasFieldErrors && <p>Corrija os campos destacados à esquerda.</p>}
    </div>
  );
}

function Idle({ title, text, children }: { title: string; text: string; children?: ReactNode }) {
  return (
    <div className="panel state">
      <IconChartLine size={32} aria-hidden="true" />
      <h2>{title}</h2>
      <p>{text}</p>
      {children}
    </div>
  );
}

interface Props { active: boolean }

/**
 * Fase 13.1: cruzamento semaforizado com duas aproximações que dividem o mesmo ciclo. Simula um plano, compara planos
 * (com IC pareado), varre a divisão do verde e estima/valida os parâmetros a partir das planilhas do vídeo.
 */
export function TrafficTab({ active }: Props) {
  const [mode, setMode] = useState<Mode | "">("");
  const [form, setForm] = useState<TrafficText>(blankTraffic);
  const [errors, setErrors] = useState<TrafficErrors>({});
  const [plans, setPlans] = useState<PlanText[]>(() => [blankPlan(1)]);
  const nextId = useRef(2);
  const [bonferroni, setBonferroni] = useState(false);
  const [sweep, setSweep] = useState<SweepText>(blankSweep);
  const [files, setFiles] = useState<VideoFiles>(blankVideoFiles);
  const [params, setParams] = useState<VideoParams>(blankVideoParams);
  const [videoMessage, setVideoMessage] = useState<string | null>(null);
  const [csv, setCsv] = useState<{ busy: boolean; error: string | null }>({ busy: false, error: null });

  const simulate = useExperiment<TrafficResult>();
  const compare = useTrafficStream<CompareResult, PlanRow>();
  const sweepRun = useTrafficStream<SweepResult, SweepPoint>();
  const estimate = useExperiment<VideoEstimate>();
  const validation = useExperiment<VideoValidation>();
  const requests = useRef<Partial<Record<"simulate" | "compare" | "sweep" | "validation", unknown>>>({});

  const names = (k: ApproachKey) => form.approaches[k === "a1" ? 0 : 1].name.trim() || (k === "a1" ? "Aproximação 1" : "Aproximação 2");
  const nameMap = { a1: names("a1"), a2: names("a2") };

  // Erros da API (422) viram mensagens nos campos; editar o formulário não reabre os antigos.
  const states = [simulate.state, compare.state, sweepRun.state, estimate.state, validation.state];
  const apiErrors = states.map((s) => (s.status === "error" ? s.error : null));
  useEffect(() => {
    const error = apiErrors.find((e) => e && e.fields?.length);
    if (error) setErrors(trafficErrors(error.fields, plans.map((p) => p.id)));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [states.map((s) => s.status).join(",")]);

  const clearError = useCallback((key: string) => setErrors(({ [key]: _gone, ...rest }) => rest), []);
  const edit = (next: TrafficText) => {
    // limpa o erro dos campos que mudaram
    const changed = (Object.keys(next) as (keyof TrafficText)[]).filter((k) => k !== "approaches" && next[k] !== form[k]);
    changed.forEach((k) => clearError(String(k)));
    next.approaches.forEach((a, i) => (Object.keys(a) as (keyof typeof a)[]).forEach((k) => {
      if (a[k] !== form.approaches[i][k]) setErrors(({ [`a${i + 1}.${k}`]: _g, ...rest }) => rest);
    }));
    setForm(next);
  };

  const fail = (built: Extract<Built, { ok: false }>) => { setErrors(built.errors); };

  const runSimulate = (e: FormEvent) => {
    e.preventDefault();
    const built = buildTrafficBody(form);
    if (!built.ok) return fail(built);
    setErrors({});
    setCsv({ busy: false, error: null });
    requests.current.simulate = built.body;
    void simulate.run((signal) => simulateTraffic(built.body, signal));
  };

  const runCompare = (e: FormEvent) => {
    e.preventDefault();
    const built = buildComparisonBody(form, plans, bonferroni);
    if (!built.ok) return fail(built);
    setErrors({});
    setCsv({ busy: false, error: null });
    requests.current.compare = built.body;
    void compare.run(async (signal, push) => {
      let final: CompareResult | null = null;
      await streamTraffic("/api/traffic/compare", built.body, (ev) => {
        if (ev.type === "start") push(0, ev.total ?? 0);
        else if ((ev.type === "base" || ev.type === "plan") && ev.plan) push(ev.completed ?? 0, ev.total ?? 0, ev.plan);
        else if (ev.type === "done") final = ev.result as CompareResult;
      }, signal);
      if (!final) throw new ApiError("http", "A API encerrou a comparação sem o resultado.");
      return final;
    });
  };

  const runSweep = (e: FormEvent) => {
    e.preventDefault();
    const built = buildSweepBody(form, sweep);
    if (!built.ok) return fail(built);
    setErrors({});
    setCsv({ busy: false, error: null });
    requests.current.sweep = built.body;
    void sweepRun.run(async (signal, push) => {
      let final: SweepResult | null = null;
      await streamTraffic("/api/traffic/sweep", built.body, (ev) => {
        if (ev.type === "start") push(0, ev.total ?? 0);
        else if (ev.type === "point" && ev.point) push(ev.completed ?? 0, ev.total ?? 0, ev.point);
        else if (ev.type === "done") final = ev.result as SweepResult;
      }, signal);
      if (!final) throw new ApiError("http", "A API encerrou a varredura sem o resultado.");
      return final;
    });
  };

  const runEstimate = (e: FormEvent) => {
    e.preventDefault();
    const body = videoForm(files, params);
    if (typeof body === "string") { setVideoMessage(body); return; }
    setVideoMessage(null);
    void estimate.run((signal) => estimateVideo(body, signal));
  };

  const runValidation = () => {
    const body = videoForm(files, params);
    if (typeof body === "string") { setVideoMessage(body); return; }
    const built = buildTrafficBody(form);
    if (!built.ok) {
      setErrors(built.errors);
      setVideoMessage("Para validar, o modelo precisa estar completo: use “Usar no formulário” e preencha o que faltar (o intervalo h e o plano).");
      return;
    }
    setVideoMessage(null);
    const config = {
      phases: built.body.phases, offset: built.body.offset,
      approaches: (built.body.approaches as Record<string, unknown>[]).map(({ lambda: _l, profile: _p, ...rest }) => rest),
    };
    body.append("config", JSON.stringify(config));
    body.append("replications", String(built.body.replications ?? 30));
    if (built.body.seed !== undefined && built.body.seed !== null) body.append("seed", String(built.body.seed));
    requests.current.validation = config;
    void validation.run((signal) => validateVideo(body, signal));
  };

  const applyToForm = (est: VideoEstimate) => {
    setForm((current) => applyEstimate(current, est));
    setErrors({});
    setMode("simulate");
  };

  const exportCsv = async (kind: "simulate" | "compare" | "sweep", seed: number) => {
    setCsv({ busy: true, error: null });
    try {
      const { path, file } = CSV_PATH[kind];
      // A semente que a API usou vai junto: sem ela, um pedido sem semente geraria outro resultado.
      const blob = await exportTrafficCsv(path, { ...(requests.current[kind] as object), seed });
      downloadBlob(blob, file);
      setCsv({ busy: false, error: null });
    } catch (e) {
      setCsv({ busy: false, error: e instanceof ApiError ? e.message : "Não foi possível exportar o CSV." });
    }
  };

  const busy = (mode === "simulate" && simulate.state.status === "loading") || (mode === "compare" && compare.state.status === "loading")
    || (mode === "sweep" && sweepRun.state.status === "loading") || (mode === "video" && estimate.state.status === "loading");
  const cancel = mode === "simulate" ? simulate.cancel : mode === "compare" ? compare.cancel : mode === "sweep" ? sweepRun.cancel : estimate.cancel;
  const onSubmit = mode === "simulate" ? runSimulate : mode === "compare" ? runCompare : mode === "sweep" ? runSweep : runEstimate;
  const runLabel = mode === "simulate" ? "Simular" : mode === "compare" ? "Comparar planos" : mode === "sweep" ? "Varrer o verde" : "Estimar com o vídeo";

  const saveRow = (type: TrafficSnapshot["type"], request: unknown, result: object, csvKind?: "simulate" | "compare" | "sweep", seed?: number) => (
    <div className="save-row">
      <SaveButton suggestedTitle={TRAFFIC_TITLE[type]} build={(t) => trafficRecord(type, request, result, t ?? TRAFFIC_TITLE[type])} />
      {csvKind && seed !== undefined && (
        <button type="button" className="btn btn-small" disabled={csv.busy} onClick={() => void exportCsv(csvKind, seed)}>
          <IconDownload size={15} aria-hidden="true" /> {csv.busy ? "Exportando…" : "Exportar CSV"}
        </button>
      )}
      {csv.error && <span className="field-error" role="alert">{csv.error}</span>}
    </div>
  );

  const streamArea = <R, P,>(
    s: ExperimentState<R>, progress: StreamProgress<P>, idle: [string, string], what: string,
    render: (result: R) => JSX.Element, renderPartial: (partial: P[]) => JSX.Element | null,
  ) => {
    if (s.status === "idle") return <Idle title={idle[0]} text={idle[1]} />;
    if (s.status === "loading") {
      return (
        <div className="panel results">
          <div className="tab-panel">
            <p role="status" aria-live="polite" className="sub">{what}…</p>
            <Progress completed={progress.completed} total={progress.total} what="itens" />
            {renderPartial(progress.partial)}
          </div>
        </div>
      );
    }
    if (s.status === "error") return <ErrorPanel error={s.error} hasFieldErrors={Object.keys(errors).length > 0} />;
    return <div className="panel results"><div className="tab-panel">{render(s.result)}</div></div>;
  };

  const validationIds = (r: VideoValidation): Record<ApproachKey, string> => ({ a1: r.approaches.a1.approach_id, a2: r.approaches.a2.approach_id });

  return (
    <div className="exp-grid" hidden={!active} role="tabpanel" id="traffic-panel" aria-label="Cruzamento">
      <form className="panel params" aria-label="Parâmetros do cruzamento semaforizado" onSubmit={onSubmit}>
        <p className="sub">
          Cruzamento com duas aproximações que dividem o mesmo ciclo semafórico fixo. Os tempos medidos no vídeo não têm valor padrão: o que ficar vazio
          é tratado como “não informado”, com aviso no resultado.
        </p>
        <div className="field traffic-mode-field">
          <label htmlFor="traffic-mode">O que fazer</label>
          <select id="traffic-mode" value={mode} onChange={(event) => { setMode(event.target.value as Mode | ""); setErrors({}); }}>
            <option value="">Escolha uma opção</option>
            {MODES.map((m) => <option key={m.key} value={m.key}>{m.label}</option>)}
          </select>
        </div>

        {mode !== "" && (
          <>
            {mode === "video" && (
              <>
                <VideoPanel files={files} params={params} onFiles={setFiles} onParams={setParams} />
                {videoMessage && <span className="field-error" role="alert">{videoMessage}</span>}
              </>
            )}
            <div className="actions">
              <button type="button" className="btn btn-small" onClick={() => { setForm(exampleTraffic()); setErrors({}); }}>
                Carregar exemplo ilustrativo
              </button>
            </div>
            <p className="field-hint">O exemplo usa valores hipotéticos só para conhecer a tela; não são medições de nenhum cruzamento.</p>

            <TrafficForm value={form} errors={errors} onChange={edit} />
            {mode === "compare" && (
              <PlansPanel plans={plans} errors={errors} bonferroni={bonferroni} onChange={setPlans} onBonferroni={setBonferroni} nextId={() => nextId.current++} />
            )}
            {mode === "sweep" && <SweepPanel value={sweep} errors={errors} onChange={(v) => { setSweep(v); setErrors({}); }} />}

            <div className="actions spaced">
              <RunButtons busy={busy} label={runLabel} onCancel={cancel} />
            </div>
            {mode === "video" && (
              <button type="button" className="btn btn-block" disabled={validation.state.status === "loading"} onClick={runValidation}>
                <IconPlus size={16} aria-hidden="true" /> {validation.state.status === "loading" ? "Validando…" : "Validar o modelo com as contagens"}
              </button>
            )}
          </>
        )}
      </form>

      {mode === "" && (
        <Idle title="Escolha uma opção" text="Selecione uma ferramenta no menu para começar. Cada opção atende a uma necessidade diferente:">
          <ul className="traffic-guide">
            <li><strong>Simular:</strong> informe os tempos do semáforo e os dados de chegada e descarga das duas aproximações para estimar filas, atrasos e vazão.</li>
            <li><strong>Comparar planos:</strong> altere tempos em um ou mais planos e compare os resultados com o plano de referência.</li>
            <li><strong>Varrer o verde:</strong> defina os limites mínimos e teste diferentes divisões do tempo verde para encontrar um equilíbrio melhor.</li>
            <li><strong>Dados do vídeo:</strong> carregue as planilhas de coleta para estimar o plano e as chegadas observadas; depois, você pode validar a simulação com as contagens.</li>
          </ul>
          <p>Se quiser conhecer os campos antes de inserir medições, escolha uma ferramenta e use “Carregar exemplo ilustrativo”.</p>
        </Idle>
      )}

      {mode === "simulate" && (
        <ResultArea
          state={simulate.state} idleTitle="Simule o cruzamento"
          idleText="Preencha o semáforo e as duas aproximações (ou carregue o exemplo) e simule: sai a fila ao longo do tempo, o atraso e a vazão, com IC."
          loadingText="Simulando o cruzamento"
        >
          {(result) => (
            <>
              {saveRow("simulate", { ...(requests.current.simulate as object), seed: result.settings.seed }, result, "simulate", result.settings.seed)}
              <TrafficSimulationView result={result} />
            </>
          )}
        </ResultArea>
      )}

      {mode === "compare" && streamArea<CompareResult, PlanRow>(
        compare.state, compare.progress,
        ["Compare planos semafóricos", "Cada plano troca alguns tempos da referência e é simulado com as mesmas chegadas; a diferença sai com IC pareado."],
        "Comparando os planos",
        (result) => (
          <>
            {saveRow("compare", { ...(requests.current.compare as object), seed: result.settings.seed }, result, "compare", result.settings.seed)}
            <TrafficCompareView data={result} names={nameMap} />
          </>
        ),
        (partial) => {
          const base = partial.find((p) => p.role === "base") ?? null;
          return base ? (
            <TrafficCompareView
              data={{ settings: { simulation_time: 0, warmup_time: 0, replications: 0, seed: 0, confidence_level: 0.95, series_step: 0 },
                multiple_comparison: { correction: "none", comparisons: 1, confidence_level: 0.95, note: "Resultados parciais: os planos aparecem conforme ficam prontos." },
                base, plans: partial.filter((p) => p.role === "plan") }}
              names={nameMap}
            />
          ) : null;
        },
      )}

      {mode === "sweep" && streamArea<SweepResult, SweepPoint>(
        sweepRun.state, sweepRun.progress,
        ["Varra a divisão do verde", "Mantém o ciclo e redistribui o verde entre as fases: a curva do atraso mostra onde fica o melhor equilíbrio."],
        "Varrendo a divisão do verde",
        (result) => (
          <>
            {saveRow("sweep", { ...(requests.current.sweep as object), seed: result.settings.seed }, result, "sweep", result.settings.seed)}
            <TrafficSweepView data={result} names={nameMap} />
          </>
        ),
        (partial) => (partial.length > 0 ? (
          <p className="note">Pontos prontos (verde da fase 1): {partial.map((p) => p.green[0].toLocaleString("pt-BR")).join(", ")} s.</p>
        ) : null),
      )}

      {mode === "video" && (
        <div className="video-results">
          <ResultArea
            state={estimate.state} idleTitle="Estime com o vídeo"
            idleText="Envie os CSV do protocolo de coleta: saem o plano semafórico, as chegadas por bloco, o tempo do 1º veículo e o intervalo entre veículos."
            loadingText="Lendo as planilhas"
            errorTitles={{ invalid_dataset: "Arquivo inválido" }}
          >
            {(result) => (
              <>
                <div className="save-row">
                  <button type="button" className="btn btn-primary btn-small" onClick={() => applyToForm(result)}>Usar no formulário</button>
                </div>
                <VideoEstimateView estimate={result} />
              </>
            )}
          </ResultArea>
          {validation.state.status !== "idle" && (
            <ResultArea state={validation.state} idleTitle="" idleText="" loadingText="Validando o modelo com as contagens">
              {(result) => (
                <>
                  {saveRow("validation", requests.current.validation, result)}
                  <h2 className="group-title">Validação: simulado × observado</h2>
                  <TrafficValidationView result={result} ids={validationIds(result)} />
                </>
              )}
            </ResultArea>
          )}
        </div>
      )}
    </div>
  );
}
