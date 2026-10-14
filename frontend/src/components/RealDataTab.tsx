import { useEffect, useMemo, useState, type FormEvent } from "react";
import {
  analyzeCsv, compareModel, type AnalysisResponse, type CompareResponse,
} from "../api/realdata";
import { levelChart } from "../charts/realdata";
import {
  buildAnalyzeForm, compareBody, errorsFromApi, INITIAL_TEXT, MAX_UPLOAD_BYTES, modelOptions,
  type RealDataErrors, type RealDataText, type SystemType,
} from "../domain/realdata";
import { useExperiment } from "../hooks/useExperiment";
import { useThemeColors } from "../hooks/useThemeColors";
import { ResultArea, RunButtons } from "./ExperimentParts";
import { PlotlyChart } from "./PlotlyChart";
import {
  ComparisonTable, CriteriaTable, DiagnosticList, EstimatesList, LevelsTable, RecommendationBanner, WarningList,
} from "./RealDataParts";
import { TextField } from "./TextField";

const SYSTEM_OPTIONS: { value: SystemType; label: string }[] = [
  { value: "auto", label: "Detectar pelos dados" },
  { value: "closed", label: "Fechado (número fixo de usuários)" },
  { value: "open", label: "Aberto (chegadas independentes)" },
];

const CONTEXT_FIELDS: (keyof RealDataText)[] = ["systemType", "servers", "serviceTime", "thinkTime", "capacity", "trimStart", "trimEnd"];

function Results({ result }: { result: AnalysisResponse }) {
  const colors = useThemeColors();
  const options = useMemo(() => modelOptions(result), [result]);
  const initialKey = (result.recommended ?? result.nearest)?.key ?? null;
  const [selected, setSelected] = useState<string | null>(initialKey);
  const { state, run } = useExperiment<CompareResponse>();

  const choose = (key: string) => {
    setSelected(key);
    const option = options.find((o) => o.key === key);
    if (key !== initialKey && option && !option.disabled) void run((signal) => compareModel(compareBody(result, option), signal));
  };

  const shown = selected === initialKey ? result.comparison : state.status === "success" ? state.result.comparison : null;
  const wChart = useMemo(() => levelChart(result, shown ?? [], "W", colors), [result, shown, colors]);
  const xChart = useMemo(() => levelChart(result, shown ?? [], "throughput", colors), [result, shown, colors]);
  const rows = result.dataset.rows_analyzed;

  return (
    <>
      <RecommendationBanner result={result} />
      <p className="note">
        {rows.toLocaleString("pt-BR")} amostras analisadas
        {result.dataset.rows !== rows ? ` (de ${result.dataset.rows.toLocaleString("pt-BR")} no arquivo)` : ""};
        {" "}teste classificado como {result.system_type === "closed" ? "fechado" : "aberto"}.
      </p>
      <WarningList warnings={result.warnings} estimates={result.estimates} />
      <CriteriaTable ranking={result.ranking} />
      <EstimatesList estimates={result.estimates} />
      <DiagnosticList diagnostics={result.diagnostics} />
      <LevelsTable levels={result.levels} />

      <div className="block">
        <h3 className="group-title">Medição × modelo</h3>
        <div className="exp-controls">
          <div className="field inline">
            <label htmlFor="rd-model">Modelo comparado</label>
            <select id="rd-model" value={selected ?? ""} onChange={(e) => choose(e.target.value)}>
              {options.map((o) => (
                <option key={o.key} value={o.key} disabled={o.disabled !== null}>
                  {o.notation}{o.disabled ? ` (${o.disabled})` : ""}
                </option>
              ))}
            </select>
          </div>
        </div>
        {state.status === "loading" && <p className="note" role="status">Comparando…</p>}
        {state.status === "error" && <p className="field-error" role="alert">{state.error.message}</p>}
        {shown ? (
          <>
            <ComparisonTable comparison={shown} />
            <p className="note">
              Erro relativo = |modelo − medido| / medido. L̂ ≈ X̂·W̄ vale por definição (lei de Little): não é uma validação independente.
            </p>
            <PlotlyChart data={wChart.data} layout={wChart.layout} label="Tempo médio de resposta medido e previsto pelo modelo, por nível de usuários" />
            <PlotlyChart data={xChart.data} layout={xChart.layout} label="Vazão medida e prevista pelo modelo, por nível de usuários" />
          </>
        ) : null}
      </div>
    </>
  );
}

/**
 * Fase 7: carrega o CSV do JMeter, verifica os dados e recomenda o modelo de filas de melhor ajuste.
 * Mesmo padrão dos experimentos: formulário à esquerda, resultado à direita.
 */
export function RealDataTab() {
  const [file, setFile] = useState<File | null>(null);
  const [text, setText] = useState<RealDataText>(INITIAL_TEXT);
  const [errors, setErrors] = useState<RealDataErrors>({});
  const { state, run, cancel } = useExperiment<AnalysisResponse>();

  useEffect(() => {
    if (state.status === "error") setErrors(errorsFromApi(state.error.fields));
  }, [state]);

  const edit = (field: keyof RealDataText) => (value: string) => {
    setText((t) => ({ ...t, [field]: value }));
    setErrors(({ [field]: _gone, ...rest }) => rest);
  };

  const submit = (e: FormEvent) => {
    e.preventDefault();
    const built = buildAnalyzeForm(file, text);
    if (!built.ok) {
      setErrors(built.errors);
      return;
    }
    setErrors({});
    void run((signal) => analyzeCsv(built.form, signal));
  };

  const contextHasError = CONTEXT_FIELDS.some((f) => errors[f]);

  return (
    <div className="exp-grid" role="tabpanel" aria-label="Dados reais">
      <form className="panel params" aria-label="Dados do teste do JMeter" onSubmit={submit} noValidate>
        <p className="sub">
          Envie o CSV exportado pelo JMeter. O sistema verifica os dados e recomenda o modelo de filas que melhor os representa.
        </p>
        <h2 className="group-title">Arquivo</h2>
        <div className={errors.file ? "field has-error" : "field"}>
          <label htmlFor="rd-file">CSV do JMeter</label>
          <input
            id="rd-file" type="file" accept=".csv,text/csv"
            aria-invalid={errors.file ? true : undefined}
            aria-describedby="rd-file-note"
            onChange={(e) => { setFile(e.target.files?.[0] ?? null); setErrors(({ file: _gone, ...rest }) => rest); }}
          />
          {errors.file ? (
            <span id="rd-file-note" className="field-error" role="alert">{errors.file}</span>
          ) : (
            <span id="rd-file-note" className="field-hint">
              Com cabeçalho: timeStamp, elapsed, label e success (de preferência também allThreads e responseCode). Até {MAX_UPLOAD_BYTES / (1024 * 1024)} MB.
            </span>
          )}
        </div>

        <details className="context" open={contextHasError || undefined}>
          <summary>Contexto do teste (opcional)</summary>
          <p className="sub">Informe o que você já sabe; o que for informado substitui a estimativa feita pelos dados.</p>
          <div className="field">
            <label htmlFor="rd-system">Tipo de sistema</label>
            <select id="rd-system" value={text.systemType} onChange={(e) => edit("systemType")(e.target.value)}>
              {SYSTEM_OPTIONS.map((o) => <option key={o.value} value={o.value}>{o.label}</option>)}
            </select>
          </div>
          <div className="grid2 spaced">
            <TextField id="rd-servers" label="Servidores (c)" value={text.servers} error={errors.servers} onChange={edit("servers")} />
            <TextField id="rd-capacity" label="Capacidade (K)" value={text.capacity} error={errors.capacity} onChange={edit("capacity")} />
            <TextField id="rd-service" label="Tempo de serviço (s)" value={text.serviceTime} error={errors.serviceTime} onChange={edit("serviceTime")} />
            <TextField id="rd-think" label="Tempo de reflexão Z (s)" value={text.thinkTime} error={errors.thinkTime} onChange={edit("thinkTime")} />
            <TextField id="rd-trim-start" label="Descartar início (%)" value={text.trimStart} error={errors.trimStart} hint="Aquecimento" onChange={edit("trimStart")} />
            <TextField id="rd-trim-end" label="Descartar fim (%)" value={text.trimEnd} error={errors.trimEnd} hint="Encerramento" onChange={edit("trimEnd")} />
          </div>
        </details>

        <div className="actions spaced">
          <RunButtons busy={state.status === "loading"} label="Analisar arquivo" onCancel={cancel} />
        </div>
      </form>

      <ResultArea
        state={state}
        idleTitle="Nenhuma análise ainda"
        idleText="Escolha o CSV do JMeter e clique em Analisar arquivo."
        loadingText="Analisando o arquivo"
        errorTitles={{ insufficient_sample: "Poucas amostras" }}
      >
        {(result) => (
          <Results key={`${result.dataset.start}-${result.dataset.rows}-${result.recommended?.key ?? "x"}`} result={result} />
        )}
      </ResultArea>
    </div>
  );
}
