import { IconCheck, IconDeviceFloppy } from "@tabler/icons-react";
import { useEffect, useRef, useState, type FormEvent } from "react";
import { ApiError } from "../api/client";
import { createRecord, type NewRecord } from "../api/records";
import { useRecords } from "../hooks/RecordsContext";

interface Props {
  /** Monta o registro na hora de salvar (o título sugerido já vem dentro). */
  build: (title?: string) => NewRecord;
  suggestedTitle: string;
}

const FRIENDLY: Record<string, string> = {
  persistence_disabled: "O histórico não está ativado neste servidor.",
  record_limit_reached: "Você atingiu o limite de registros. Exclua algum no Histórico para salvar outro.",
  record_too_large: "Este resultado é grande demais para ser salvo.",
};

/**
 * "Salvar no histórico": pede o título (já sugerido) e grava o resultado na tela.
 * Não aparece quando o servidor não tem banco de dados.
 */
export function SaveButton({ build, suggestedTitle }: Props) {
  const { availability, openHistory } = useRecords();
  const [editing, setEditing] = useState(false);
  const [title, setTitle] = useState(suggestedTitle);
  const [status, setStatus] = useState<"idle" | "saving" | "saved">("idle");
  const [error, setError] = useState<string | null>(null);
  const alive = useRef(true);

  useEffect(() => {
    alive.current = true;
    return () => { alive.current = false; };
  }, []);

  if (availability !== "enabled") return null;

  const start = () => {
    setTitle(suggestedTitle);
    setError(null);
    setStatus("idle");
    setEditing(true);
  };

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    const clean = title.trim();
    if (!clean) { setError("Informe um título."); return; }
    setStatus("saving");
    setError(null);
    try {
      await createRecord(build(clean));
      if (!alive.current) return;
      setStatus("saved");
      setEditing(false);
    } catch (err) {
      if (!alive.current) return;
      setStatus("idle");
      const code = err instanceof ApiError ? err.code : "http";
      setError(FRIENDLY[code] ?? (err instanceof ApiError ? err.message : "Não foi possível salvar."));
    }
  };

  if (editing) {
    return (
      <form className="save-bar" aria-label="Salvar no histórico" onSubmit={(e) => void submit(e)}>
        <label htmlFor="save-title" className="save-label">Título</label>
        <input
          id="save-title" type="text" value={title} maxLength={120} autoFocus
          onChange={(e) => { setTitle(e.target.value); setError(null); }}
        />
        <button type="submit" className="btn btn-small btn-primary" disabled={status === "saving"}>
          {status === "saving" ? "Salvando…" : "Salvar"}
        </button>
        <button type="button" className="btn btn-small" onClick={() => setEditing(false)} disabled={status === "saving"}>
          Cancelar
        </button>
        {error && <span className="field-error" role="alert">{error}</span>}
      </form>
    );
  }

  return (
    <div className="save-bar">
      <button type="button" className="btn btn-small" onClick={start}>
        <IconDeviceFloppy size={15} aria-hidden="true" />Salvar no histórico
      </button>
      {status === "saved" && (
        <span className="save-ok" role="status">
          <IconCheck size={15} aria-hidden="true" />Salvo.{" "}
          <button type="button" className="link-button" onClick={openHistory}>Ver no Histórico</button>
        </span>
      )}
      {error && <span className="field-error" role="alert">{error}</span>}
    </div>
  );
}
