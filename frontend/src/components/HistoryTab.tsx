import { IconHistory } from "@tabler/icons-react";
import { useCallback, useEffect, useState, type FormEvent } from "react";
import type { FitResult } from "../api/analysis";
import type { AnalysisResponse } from "../api/realdata";
import { ApiError } from "../api/client";
import {
  deleteRecord, getRecord, listRecords, renameRecord,
  type RecordDetail, type RecordKind, type RecordSummary,
} from "../api/records";
import {
  KIND_LABELS, KIND_ORDER, parseExperimentRecord, parseFitRecord, parseLabRecord, parseRealDataRecord,
  type ExperimentSnapshot, type LabSnapshot,
} from "../domain/records";
import { useRecords } from "../hooks/RecordsContext";
import { FitResultView } from "./FitResultView";
import { SensitivityResult } from "./SensitivityPanel";
import { ServersResult } from "./ServersPanel";
import { ServicesResult } from "./ServicesPanel";
import { ScenariosView } from "./ScenariosView";
import { SizingResultView } from "./SizingTab";
import { SweepResult } from "./SweepPanel";
import { RealDataResults } from "./RealDataTab";

const PAGE = 20;

const dateFormat = new Intl.DateTimeFormat("pt-BR", { dateStyle: "short", timeStyle: "short" });
const formatDate = (iso: string) => dateFormat.format(new Date(iso));
const formatSize = (bytes: number) => (bytes < 1024 ? `${bytes} B` : `${(bytes / 1024).toFixed(1)} KB`);

/** As mensagens da API já são em português e dizem o que fazer (ex.: aplicar as migrações). */
function messageOf(error: unknown): string {
  return error instanceof ApiError ? error.message : "Erro inesperado.";
}

interface Props {
  /** Recoloca um resultado do Laboratório (formulário e resultado) e vai para a aba. */
  onReopenLab: (snapshot: LabSnapshot) => void;
}

type Viewer =
  | { kind: "lab"; record: RecordDetail; snapshot: LabSnapshot }
  | { kind: "experiment"; record: RecordDetail; snapshot: ExperimentSnapshot }
  | { kind: "realdata"; record: RecordDetail; analysis: AnalysisResponse }
  | { kind: "fit"; record: RecordDetail; fit: FitResult }
  | { kind: "unknown"; record: RecordDetail };

function toViewer(record: RecordDetail): Viewer {
  const lab = parseLabRecord(record);
  if (lab) return { kind: "lab", record, snapshot: lab };
  const fit = parseFitRecord(record);
  if (fit) return { kind: "fit", record, fit };
  const experiment = parseExperimentRecord(record);
  if (experiment) return { kind: "experiment", record, snapshot: experiment };
  const analysis = parseRealDataRecord(record);
  if (analysis) return { kind: "realdata", record, analysis };
  return { kind: "unknown", record };
}

function ExperimentView({ snapshot }: { snapshot: ExperimentSnapshot }) {
  if (snapshot.type === "sweep") return <SweepResult result={snapshot.result} />;
  if (snapshot.type === "servers") return <ServersResult result={snapshot.result} model={snapshot.model} />;
  if (snapshot.type === "services") return <ServicesResult result={snapshot.result} model={snapshot.model} />;
  if (snapshot.type === "sizing") {
    return <SizingResultView action={snapshot.action} result={snapshot.result} costUnit={snapshot.costUnit} />;
  }
  if (snapshot.type === "scenarios") return <ScenariosView data={snapshot.result} />;
  return <SensitivityResult result={snapshot.result} model={snapshot.model} />;
}

export function HistoryTab({ onReopenLab }: Props) {
  const { availability, limits } = useRecords();
  const [kind, setKind] = useState<RecordKind | "">("");
  const [items, setItems] = useState<RecordSummary[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [opening, setOpening] = useState<string | null>(null);
  const [viewer, setViewer] = useState<Viewer | null>(null);
  const [renaming, setRenaming] = useState<{ id: string; title: string } | null>(null);
  const [confirmDelete, setConfirmDelete] = useState<string | null>(null);

  const load = useCallback(async (offset: number, replace: boolean) => {
    setLoading(true);
    setError(null);
    try {
      const page = await listRecords({ kind: kind || undefined, limit: PAGE, offset });
      setItems((current) => (replace ? page.items : [...current, ...page.items]));
      setTotal(page.total);
    } catch (e) {
      setError(messageOf(e));
    } finally {
      setLoading(false);
    }
  }, [kind]);

  useEffect(() => {
    if (availability === "enabled") void load(0, true);
  }, [availability, load]);

  if (availability === "checking") {
    return <div className="panel state" role="status"><div className="spinner" aria-hidden="true" /><p>Verificando o histórico…</p></div>;
  }
  if (availability === "disabled") {
    return (
      <div className="panel state">
        <IconHistory size={32} aria-hidden="true" />
        <h2>Histórico indisponível</h2>
        <p>
          Este servidor não tem um banco de dados configurado. Defina QSIMULADOR_DATABASE_URL na API para
          salvar e reabrir resultados. O resto do QSimulador funciona normalmente.
        </p>
      </div>
    );
  }

  const open = async (id: string) => {
    setOpening(id);
    setError(null);
    try {
      setViewer(toViewer(await getRecord(id)));
    } catch (e) {
      setError(messageOf(e));
    } finally {
      setOpening(null);
    }
  };

  const submitRename = async (e: FormEvent) => {
    e.preventDefault();
    if (!renaming) return;
    const title = renaming.title.trim();
    if (!title) { setError("Informe um título."); return; }
    try {
      const updated = await renameRecord(renaming.id, title);
      setItems((current) => current.map((i) => (i.id === updated.id ? updated : i)));
      setViewer((v) => (v && v.record.id === updated.id ? { ...v, record: { ...v.record, title: updated.title } } : v));
      setRenaming(null);
      setError(null);
    } catch (err) {
      setError(messageOf(err));
    }
  };

  const remove = async (id: string) => {
    try {
      await deleteRecord(id);
      setItems((current) => current.filter((i) => i.id !== id));
      setTotal((t) => Math.max(0, t - 1));
      setViewer((v) => (v && v.record.id === id ? null : v));
      setConfirmDelete(null);
      setError(null);
    } catch (err) {
      setError(messageOf(err));
      setConfirmDelete(null);
    }
  };

  return (
    <div className="history">
      <div className="panel history-list">
        <div className="history-head">
          <h2 className="group-title">Resultados salvos</h2>
          <div className="field inline">
            <label htmlFor="history-kind">Tipo</label>
            <select id="history-kind" value={kind} onChange={(e) => { setKind(e.target.value as RecordKind | ""); setViewer(null); }}>
              <option value="">Todos</option>
              {KIND_ORDER.map((k) => <option key={k} value={k}>{KIND_LABELS[k]}</option>)}
            </select>
          </div>
        </div>
        {limits && (
          <p className="note">Este navegador pode guardar até {limits.max_records_per_client} resultados. Eles ficam ligados a este navegador, sem login.</p>
        )}
        {error && <p className="field-error" role="alert">{error}</p>}

        {items.length === 0 && !loading && !error && (
          <p className="empty-note">Nenhum resultado salvo{kind ? " deste tipo" : ""}. Use “Salvar no histórico” em um resultado.</p>
        )}

        <ul className="history-items" aria-label="Resultados salvos">
          {items.map((item) => (
            <li key={item.id} className={viewer?.record.id === item.id ? "history-item is-open" : "history-item"}>
              {renaming?.id === item.id ? (
                <form className="save-bar" aria-label="Renomear" onSubmit={(e) => void submitRename(e)}>
                  <label htmlFor={`rename-${item.id}`} className="save-label">Novo título</label>
                  <input
                    id={`rename-${item.id}`} type="text" value={renaming.title} maxLength={120} autoFocus
                    onChange={(e) => setRenaming({ id: item.id, title: e.target.value })}
                  />
                  <button type="submit" className="btn btn-small btn-primary">Salvar título</button>
                  <button type="button" className="btn btn-small" onClick={() => setRenaming(null)}>Cancelar</button>
                </form>
              ) : (
                <>
                  <div className="history-main">
                    <strong>{item.title}</strong>
                    <span className="note">
                      {KIND_LABELS[item.kind]} · {formatDate(item.created_at)} · {formatSize(item.size_bytes)}
                    </span>
                  </div>
                  <div className="history-actions">
                    <button type="button" className="btn btn-small" disabled={opening === item.id} onClick={() => void open(item.id)}>
                      {opening === item.id ? "Abrindo…" : "Abrir"}
                    </button>
                    <button type="button" className="btn btn-small" onClick={() => setRenaming({ id: item.id, title: item.title })}>
                      Renomear
                    </button>
                    {confirmDelete === item.id ? (
                      <>
                        <button type="button" className="btn btn-small btn-danger" onClick={() => void remove(item.id)}>Confirmar exclusão</button>
                        <button type="button" className="btn btn-small" onClick={() => setConfirmDelete(null)}>Cancelar</button>
                      </>
                    ) : (
                      <button type="button" className="btn btn-small" onClick={() => setConfirmDelete(item.id)}>Excluir</button>
                    )}
                  </div>
                </>
              )}
            </li>
          ))}
        </ul>

        {loading && <p className="note" role="status">Carregando…</p>}
        {items.length < total && !loading && (
          <button type="button" className="btn btn-small" onClick={() => void load(items.length, false)}>
            Carregar mais ({items.length} de {total})
          </button>
        )}
      </div>

      {viewer && (
        <div className="panel results history-view" aria-label="Registro aberto">
          <div className="tab-panel">
            <h2 className="group-title">{viewer.record.title}</h2>
            <p className="note">
              {KIND_LABELS[viewer.record.kind]} · salvo em {formatDate(viewer.record.created_at)}
            </p>
            {viewer.kind === "lab" && (
              <div className="actions spaced">
                <button type="button" className="btn btn-primary" onClick={() => onReopenLab(viewer.snapshot)}>
                  Reabrir no Laboratório
                </button>
              </div>
            )}
            {viewer.kind === "experiment" && <ExperimentView snapshot={viewer.snapshot} />}
            {viewer.kind === "fit" && <FitResultView result={viewer.fit} />}
            {viewer.kind === "realdata" && <RealDataResults result={viewer.analysis} />}
            {viewer.kind === "unknown" && (
              <p className="field-error" role="alert">
                Não foi possível reabrir este registro: o formato dos dados não é reconhecido por esta versão.
              </p>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
