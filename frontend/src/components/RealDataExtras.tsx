import { IconDownload } from "@tabler/icons-react";
import { useEffect, useMemo, useState, type FormEvent } from "react";
import { ApiError } from "../api/client";
import { compareModel, type CompareResponse } from "../api/realdata";
import {
  buildReport, compareSimulated, importLevels, type LevelsImport, type ReportBody, type SimulatedCompareResponse,
} from "../api/realdataExtra";
import { levelChart } from "../charts/realdata";
import {
  applySuggestions, buildLevelsCompare, buildLevelsForm, INITIAL_LEVELS, INITIAL_SIM, LEVELS_MODELS,
  levelsErrorsFromApi, needsCapacity, needsServers, needsThinkTime,
  type LevelsErrors, type LevelsText, type SimulationErrors, type SimulationText,
} from "../domain/realdataExtra";
import { MAX_UPLOAD_BYTES } from "../domain/realdata";
import { formatNumber } from "../domain/format";
import { useExperiment } from "../hooks/useExperiment";
import { useThemeColors } from "../hooks/useThemeColors";
import { ResultArea, RunButtons } from "./ExperimentParts";
import { PlotlyChart } from "./PlotlyChart";
import { ComparisonTable, LevelsTable } from "./RealDataParts";
import { TextField } from "./TextField";

/** Baixa um texto como arquivo (relatório). */
function saveText(filename: string, mediaType: string, content: string) {
  const url = URL.createObjectURL(new Blob([content], { type: mediaType }));
  const link = document.createElement("a");
  link.href = url;
  link.download = filename;
  link.click();
  URL.revokeObjectURL(url);
}

/** Opção "Simular também": desligada por padrão, para a comparação continuar só analítica. */
export function SimulationOptions({
  idPrefix, value, errors, onChange,
}: {
  idPrefix: string; value: SimulationText; errors: SimulationErrors; onChange: (next: SimulationText) => void;
}) {
  const edit = (key: keyof SimulationText) => (text: string) => onChange({ ...value, [key]: text });
  return (
    <div className="block">
      <label className="check">
        <input
          type="checkbox" checked={value.enabled}
          onChange={(e) => onChange({ ...value, enabled: e.target.checked })}
        />
        Simular também (medido × analítico × simulação)
      </label>
      {value.enabled && (
        <div className="grid2 spaced">
          <TextField id={`${idPrefix}-sim-time`} label="Tempo simulado (s)" value={value.simulationTime} error={errors.simulationTime} onChange={edit("simulationTime")} />
          <TextField id={`${idPrefix}-sim-reps`} label="Réplicas" value={value.replications} error={errors.replications} onChange={edit("replications")} />
          <TextField id={`${idPrefix}-sim-warmup`} label="Warm-up (s)" value={value.warmupTime} error={errors.warmupTime} onChange={edit("warmupTime")} />
          <TextField id={`${idPrefix}-sim-seed`} label="Semente" value={value.seed} error={errors.seed} hint="O nível i usa semente + i" onChange={edit("seed")} />
        </div>
      )}
    </div>
  );
}

/** Botões do relatório experimental (RF-44): a API monta o texto a partir dos resultados já calculados. */
export function ReportButtons({ getBody }: { getBody: () => Omit<ReportBody, "format"> }) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const download = async (format: ReportBody["format"]) => {
    setBusy(true);
    setError(null);
    try {
      const report = await buildReport({ ...getBody(), format });
      saveText(report.filename, report.media_type, report.content);
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Não foi possível gerar o relatório.");
    } finally {
      setBusy(false);
    }
  };
  return (
    <div className="block">
      <div className="rd-report" role="group" aria-label="Relatório experimental">
        <span>Relatório experimental:</span>
        <button type="button" className="btn btn-small" disabled={busy} onClick={() => void download("markdown")}>
          <IconDownload size={14} aria-hidden="true" /> Markdown (.md)
        </button>
        <button type="button" className="btn btn-small" disabled={busy} onClick={() => void download("html")}>
          <IconDownload size={14} aria-hidden="true" /> HTML
        </button>
      </div>
      {error && <p className="field-error" role="alert">{error}</p>}
    </div>
  );
}

/** Texto padrão que acompanha a tabela quando há simulação. */
export const SIMULATION_NOTE =
  "Simulação: média das réplicas e seu IC; “Simulação no IC do medido” indica se a média simulada cai dentro do IC do medido.";

function LevelsResults({
  imported, compared,
}: {
  imported: LevelsImport;
  compared: ReturnType<typeof useExperiment<SimulatedCompareResponse | CompareResponse>>["state"];
}) {
  const colors = useThemeColors();
  const comparison = compared.status === "success" ? compared.result.comparison : null;
  const wChart = useMemo(() => levelChart(imported, comparison ?? [], "W", colors), [imported, comparison, colors]);
  const xChart = useMemo(() => levelChart(imported, comparison ?? [], "throughput", colors), [imported, comparison, colors]);
  const s = imported.suggestions;
  const hasSim = compared.status === "success" && "simulation" in compared.result && Boolean(compared.result.simulation);
  return (
    <>
      <section className="block" aria-label="Níveis importados">
        <h2 className="group-title">Níveis de carga importados</h2>
        <LevelsTable levels={imported.levels} />
        <p className="note">
          Calibração sugerida no menor nível ({s.base_users} usuário{s.base_users === 1 ? "" : "s"}):
          {" "}μ = {s.mu == null ? "—" : `${formatNumber(Number(s.mu.toPrecision(4)))} req/s`}
          {s.think_time != null ? `; Z = ${formatNumber(Number(s.think_time.toPrecision(4)))} s` : ""}.
        </p>
        {imported.warnings.map((w) => <p key={w} className="note">{w}</p>)}
      </section>

      <section className="block" aria-label="Comparação dos níveis com o modelo">
        <h2 className="group-title">Medição × modelo</h2>
        {compared.status === "idle" && <p className="note">Escolha o modelo à esquerda e clique em Comparar com o modelo.</p>}
        {compared.status === "loading" && <p className="note" role="status">Comparando…</p>}
        {compared.status === "error" && <p className="field-error" role="alert">{compared.error.message}</p>}
        {comparison && (
          <>
            <ComparisonTable comparison={comparison} />
            <p className="note">
              Erro relativo = |modelo − medido| / medido. L̂ = X̂·W̄ vale por definição (lei de Little). Sem amostras, não há IC do medido.
              {hasSim ? ` ${SIMULATION_NOTE}` : ""}
            </p>
            <PlotlyChart data={wChart.data} layout={wChart.layout} label="Tempo médio de resposta medido e previsto pelo modelo, por nível de usuários" />
            <PlotlyChart data={xChart.data} layout={xChart.layout} label="Vazão medida e prevista pelo modelo, por nível de usuários" />
          </>
        )}
        <ReportButtons
          getBody={() => ({
            levels_import: imported,
            ...(compared.status === "success" ? { comparison: compared.result } : {}),
          })}
        />
      </section>
    </>
  );
}

/**
 * Segunda origem de dados (RF-43): CSV agregado por nível de carga (users, avg_ms, p90_ms, throughput, error_rate).
 * Os níveis importados têm o mesmo formato do `levels` da análise do JTL e alimentam a mesma comparação.
 */
export function LevelsTab() {
  const [file, setFile] = useState<File | null>(null);
  const [text, setText] = useState<LevelsText>(INITIAL_LEVELS);
  const [errors, setErrors] = useState<LevelsErrors & SimulationErrors>({});
  const [sim, setSim] = useState<SimulationText>(INITIAL_SIM);
  const imported = useExperiment<LevelsImport>();
  const compared = useExperiment<SimulatedCompareResponse | CompareResponse>();

  useEffect(() => {
    const state = imported.state;
    if (state.status === "success") setText((t) => applySuggestions(t, state.result.suggestions));
    if (state.status === "error") setErrors(levelsErrorsFromApi(state.error.fields));
  }, [imported.state]);

  useEffect(() => {
    if (compared.state.status === "error") setErrors(levelsErrorsFromApi(compared.state.error.fields));
  }, [compared.state]);

  const edit = (key: keyof LevelsText) => (value: string) => {
    setText((t) => ({ ...t, [key]: value }));
    setErrors(({ [key]: _gone, ...rest }) => rest);
  };

  const submitFile = (e: FormEvent) => {
    e.preventDefault();
    const built = buildLevelsForm(file);
    if (!built.ok) { setErrors({ file: built.error }); return; }
    setErrors({});
    compared.cancel();
    void imported.run((signal) => importLevels(built.form, signal));
  };

  const compare = (e: FormEvent) => {
    e.preventDefault();
    if (imported.state.status !== "success") return;
    const built = buildLevelsCompare(imported.state.result.levels, text, sim);
    if (!built.ok) { setErrors(built.errors); return; }
    setErrors({});
    void compared.run((signal) => (
      "simulation" in built.body ? compareSimulated(built.body, signal) : compareModel(built.body, signal)
    ));
  };

  const loaded = imported.state.status === "success";

  return (
    <div className="exp-grid" role="tabpanel" aria-label="Níveis de carga">
      <div className="panel params">
        <form aria-label="Níveis de carga do teste" onSubmit={submitFile} noValidate>
          <p className="sub">
            Envie um CSV com um teste por linha. Com o menor nível de carga, o sistema sugere μ e Z; depois compara toda a curva com o modelo.
          </p>
          <h2 className="group-title">Arquivo</h2>
          <div className={errors.file ? "field has-error" : "field"}>
            <label htmlFor="lv-file">CSV de níveis de carga</label>
            <input
              id="lv-file" type="file" accept=".csv,text/csv" aria-describedby="lv-file-note"
              aria-invalid={errors.file ? true : undefined}
              onChange={(e) => { setFile(e.target.files?.[0] ?? null); setErrors(({ file: _gone, ...rest }) => rest); }}
            />
            {errors.file ? (
              <span id="lv-file-note" className="field-error" role="alert">{errors.file}</span>
            ) : (
              <span id="lv-file-note" className="field-hint">
                Colunas: users, avg_ms, throughput (opcionais: p90_ms, error_rate). Até {MAX_UPLOAD_BYTES / (1024 * 1024)} MB.
              </span>
            )}
          </div>
          <div className="actions spaced">
            <RunButtons busy={imported.state.status === "loading"} label="Importar níveis" onCancel={imported.cancel} />
          </div>
        </form>

        {loaded && (
          <form aria-label="Modelo dos níveis de carga" onSubmit={compare} noValidate>
            <h2 className="group-title">Modelo</h2>
            <div className="field">
              <label htmlFor="lv-model">Modelo dos níveis</label>
              <select id="lv-model" value={text.model} onChange={(e) => edit("model")(e.target.value)}>
                {LEVELS_MODELS.map((m) => <option key={m.key} value={m.key}>{m.label}</option>)}
              </select>
            </div>
            <div className="grid2 spaced">
              <TextField id="lv-mu" label="μ do modelo (req/s)" value={text.mu} error={errors.mu} hint="Sugerido no menor nível" onChange={edit("mu")} />
              {needsServers(text.model) && (
                <TextField id="lv-servers" label="Servidores do modelo (c)" value={text.servers} error={errors.servers} onChange={edit("servers")} />
              )}
              {needsCapacity(text.model) && (
                <TextField id="lv-capacity" label="Capacidade do modelo (K)" value={text.capacity} error={errors.capacity} onChange={edit("capacity")} />
              )}
              {needsThinkTime(text.model) && (
                <TextField id="lv-think" label="Reflexão do modelo Z (s)" value={text.thinkTime} error={errors.thinkTime} hint="Sugerido no menor nível" onChange={edit("thinkTime")} />
              )}
            </div>
            <SimulationOptions idPrefix="lv" value={sim} errors={errors} onChange={setSim} />
            <div className="actions spaced">
              <RunButtons busy={compared.state.status === "loading"} label="Comparar com o modelo" onCancel={compared.cancel} />
            </div>
          </form>
        )}
      </div>

      <ResultArea
        state={imported.state}
        idleTitle="Nenhum arquivo importado"
        idleText="Escolha o CSV de níveis de carga e clique em Importar níveis."
        loadingText="Importando o arquivo"
      >
        {(result) => <LevelsResults imported={result} compared={compared.state} />}
      </ResultArea>
    </div>
  );
}
