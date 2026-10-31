import { IconAlertTriangle, IconInfoCircle } from "@tabler/icons-react";
import type { ApproachKey, DischargeEstimate, VideoEstimate } from "../api/traffic";
import { formatSeconds } from "../domain/traffic";
import { TextField } from "./TextField";

export interface VideoFiles {
  signal: File | null; counts: File | null; crossings: File | null; trajectories: File | null;
}
export interface VideoParams { sessionId: string; approachIds: string; maxHeadway: string; minRun: string; core: string; profileBlock: string }
export const blankVideoFiles = (): VideoFiles => ({ signal: null, counts: null, crossings: null, trajectories: null });
export const blankVideoParams = (): VideoParams => ({ sessionId: "", approachIds: "", maxHeadway: "4", minRun: "5", core: "8", profileBlock: "900" });

/** Monta o multipart das rotas /video/*. Devolve a mensagem do que falta, se faltar algo. */
export function videoForm(files: VideoFiles, params: VideoParams): FormData | string {
  if (!files.signal) return "Escolha o CSV dos eventos semafóricos.";
  if (!files.counts) return "Escolha o CSV das contagens por intervalo.";
  const form = new FormData();
  form.append("signal_events", files.signal);
  form.append("counts", files.counts);
  if (files.crossings) form.append("crossings", files.crossings);
  if (files.trajectories) form.append("trajectories", files.trajectories);
  const add = (key: string, value: string) => { if (value.trim() !== "") form.append(key, value.trim().replace(",", key === "approach_ids" || key === "session_id" ? "," : ".")); };
  add("session_id", params.sessionId);
  add("approach_ids", params.approachIds);
  add("max_headway", params.maxHeadway);
  add("min_run", params.minRun);
  add("core", params.core);
  add("profile_block", params.profileBlock);
  return form;
}

function FileInput({ id, label, hint, file, onChange }: { id: string; label: string; hint: string; file: File | null; onChange: (f: File | null) => void }) {
  return (
    <div className="field">
      <label htmlFor={id}>{label}</label>
      <input id={id} type="file" accept=".csv,text/csv" onChange={(e) => onChange(e.target.files?.[0] ?? null)} />
      <span className="field-hint">{file ? file.name : hint}</span>
    </div>
  );
}

export function VideoPanel({ files, params, onFiles, onParams }: {
  files: VideoFiles; params: VideoParams; onFiles: (f: VideoFiles) => void; onParams: (p: VideoParams) => void;
}) {
  const set = (patch: Partial<VideoFiles>) => onFiles({ ...files, ...patch });
  const field = (key: keyof VideoParams, label: string, hint?: string) => (
    <TextField id={`video-${key}`} label={label} value={params[key]} hint={hint} onChange={(v) => onParams({ ...params, [key]: v })} />
  );
  return (
    <fieldset className="scenario-card">
      <legend>Planilhas do vídeo</legend>
      <p className="sub">CSV do protocolo de coleta. Nada é preenchido por suposição: célula vazia obrigatória recusa o arquivo e diz a linha.</p>
      <FileInput id="video-signal" label="Eventos semafóricos (obrigatório)" hint="Com cabeçalho: timestamp, approach_id, signal_state" file={files.signal} onChange={(f) => set({ signal: f })} />
      <FileInput id="video-counts" label="Contagens por intervalo (obrigatório)" hint="Com cabeçalho: interval_start, interval_end, approach_id, arrivals, departures, queue_count" file={files.counts} onChange={(f) => set({ counts: f })} />
      <FileInput id="video-crossings" label="Cruzamentos da linha de retenção" hint="Opcional: crossing_time, approach_id. Necessário para estimar ℓ, h e o amarelo utilizável." file={files.crossings} onChange={(f) => set({ crossings: f })} />
      <FileInput id="video-tracks" label="Veículos acompanhados" hint="Opcional: queue_arrival_time, crossing_time. Dá o atraso observado." file={files.trajectories} onChange={(f) => set({ trajectories: f })} />
      <div className="grid2">
        {field("sessionId", "Sessão", "Só se os arquivos tiverem mais de uma.")}
        {field("approachIds", "Aproximações 1 e 2", "Ex.: A,B (a 1ª é a da fase 1).")}
      </div>
      <details>
        <summary>Critérios do método (não são dados medidos)</summary>
        <p className="sub">Definem o que conta como descarga saturada na estimativa de ℓ e h. Os valores abaixo são sugestões e aparecem no resultado.</p>
        <div className="grid2">
          {field("maxHeadway", "Intervalo máximo (s)", "Acima disso a descarga deixa de contar como contínua.")}
          {field("minRun", "Veículos mínimos por verde")}
          {field("core", "Veículos da cabeça da fila usados")}
          {field("profileBlock", "Bloco do perfil (s)", "Junta as contagens em blocos (900 = 15 min).")}
        </div>
      </details>
    </fieldset>
  );
}

function DischargeRows({ k, name, d }: { k: ApproachKey; name: string; d: DischargeEstimate | undefined }) {
  if (!d) return null;
  return (
    <tr key={k}>
      <th scope="row">{name}</th>
      <td className="num">{d.saturated_cycles}</td>
      <td className="num">{d.first_vehicle_time ? `${formatSeconds(d.first_vehicle_time.mean)} [${formatSeconds(d.first_vehicle_time.ci_low)}; ${formatSeconds(d.first_vehicle_time.ci_high)}]` : "não estimado"}</td>
      <td className="num">{d.headway ? `${formatSeconds(d.headway.mean)} [${formatSeconds(d.headway.ci_low)}; ${formatSeconds(d.headway.ci_high)}]` : "não estimado"}</td>
      <td className="num">{d.headway ? d.headway.cv.toLocaleString("pt-BR", { maximumFractionDigits: 2 }) : "—"}</td>
      <td className="num">{d.amber_usable ? formatSeconds(d.amber_usable.value) : "não estimado"}</td>
    </tr>
  );
}

export function VideoEstimateView({ estimate }: { estimate: VideoEstimate }) {
  const sig = estimate.signal;
  const names: Record<ApproachKey, string> = { a1: estimate.approach_ids[0] ?? "Aproximação 1", a2: estimate.approach_ids[1] ?? "Aproximação 2" };
  const phases = sig.phases;
  const notes = [...estimate.notes, ...(estimate.discharge ? (["a1", "a2"] as ApproachKey[]).flatMap((k) => estimate.discharge![k].notes.map((n) => `${names[k]}: ${n}`)) : [])];
  const fmt = (v: number | null | undefined) => (v === null || v === undefined ? "—" : formatSeconds(v));
  return (
    <>
      <p className="sub">
        Sessão {estimate.session_id ?? "única"}, {(estimate.horizon / 60).toLocaleString("pt-BR", { maximumFractionDigits: 1 })} min de contagem.
        Estimativas a partir dos seus arquivos; o que não pôde ser estimado fica como “não estimado” e segue como <em>não informado</em> no formulário.
      </p>
      {sig.warnings.length > 0 && (
        <ul className="scn-alerts" aria-label="Avisos do plano semafórico">
          {sig.warnings.map((w) => <li key={w.code} className="alert-warn"><IconAlertTriangle size={14} aria-hidden="true" /> {w.message}</li>)}
        </ul>
      )}
      <section className="block" aria-labelledby="video-signal-title">
        <h3 id="video-signal-title">Plano semafórico observado</h3>
        <div className="table-wrap">
          <table className="table">
            <caption className="sr-only">Durações médias das fases observadas</caption>
            <thead><tr><th scope="col">Fase</th><th scope="col" className="num">Verde</th><th scope="col" className="num">Amarelo</th><th scope="col" className="num">Todo-vermelho</th></tr></thead>
            <tbody>
              {phases.map((p, i) => (
                <tr key={i}><th scope="row">Fase {i + 1} ({names[i === 0 ? "a1" : "a2"]})</th><td className="num">{fmt(p.green)}</td><td className="num">{fmt(p.amber)}</td><td className="num">{fmt(p.all_red)}</td></tr>
              ))}
            </tbody>
          </table>
        </div>
        <p className="note">
          Ciclo médio {fmt(sig.cycle.mean)} (desvio {fmt(sig.cycle.std)}, de {fmt(sig.cycle.min)} a {fmt(sig.cycle.max)}, {sig.cycle.n} ciclos).
          Offset {fmt(sig.offset)} ({sig.offset_source === "observed" ? "observado" : "extrapolado"}).
        </p>
      </section>
      <section className="block" aria-labelledby="video-arrivals-title">
        <h3 id="video-arrivals-title">Chegadas</h3>
        <div className="table-wrap">
          <table className="table">
            <caption className="sr-only">Taxa de chegada por aproximação</caption>
            <thead><tr><th scope="col">Aproximação</th><th scope="col" className="num">Chegadas</th><th scope="col" className="num">Taxa (veíc./min)</th><th scope="col" className="num">IC</th><th scope="col" className="num">Fila inicial</th></tr></thead>
            <tbody>
              {(["a1", "a2"] as ApproachKey[]).map((k) => {
                const a = estimate.arrivals[k];
                return (
                  <tr key={k}>
                    <th scope="row">{names[k]}</th><td className="num">{a.arrivals}</td>
                    <td className="num">{(a.mean_rate * 60).toLocaleString("pt-BR", { maximumFractionDigits: 2 })}</td>
                    <td className="num">[{(a.mean_rate_ci[0] * 60).toLocaleString("pt-BR", { maximumFractionDigits: 2 })}; {(a.mean_rate_ci[1] * 60).toLocaleString("pt-BR", { maximumFractionDigits: 2 })}]</td>
                    <td className="num">{a.initial_queue ?? "não informada"}</td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      </section>
      <section className="block" aria-labelledby="video-discharge-title">
        <h3 id="video-discharge-title">Descarga da fila</h3>
        {estimate.discharge ? (
          <div className="table-wrap">
            <table className="table">
              <caption className="sr-only">Tempo do primeiro veículo, intervalo entre veículos e amarelo utilizável</caption>
              <thead><tr><th scope="col">Aproximação</th><th scope="col" className="num">Verdes saturados</th><th scope="col" className="num">1º veículo (ℓ)</th><th scope="col" className="num">Intervalo h</th><th scope="col" className="num">CV de h</th><th scope="col" className="num">Amarelo utilizável</th></tr></thead>
              <tbody>
                <DischargeRows k="a1" name={names.a1} d={estimate.discharge.a1} />
                <DischargeRows k="a2" name={names.a2} d={estimate.discharge.a2} />
              </tbody>
            </table>
          </div>
        ) : <p className="note">Sem o CSV de cruzamentos da linha de retenção, ℓ, h e o amarelo utilizável não são estimados: meça no vídeo ou envie o arquivo.</p>}
        <p className="note">
          <IconInfoCircle size={14} aria-hidden="true" /> {estimate.method.note} Usado: intervalo máximo {estimate.method.max_headway} s, ao menos {estimate.method.min_run} veículos por verde,
          {" "}{estimate.method.core} veículos da cabeça da fila no ajuste. ℓ e h vêm da reta “instante do n-ésimo veículo = ℓ + (n − 1)·h” ajustada em todos os verdes.
        </p>
      </section>
      {notes.length > 0 && <ul className="scn-alerts" aria-label="Observações">{notes.map((n) => <li key={n} className="alert-warn">{n}</li>)}</ul>}
    </>
  );
}
