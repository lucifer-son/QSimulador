import { useRef, useState, type ChangeEvent } from "react";
import { MAX_SAMPLE_BYTES, MIN_SAMPLE, parseSampleFile, parseSampleText, readFileText } from "../domain/analysis";
import { fitRecord, fitTitle } from "../domain/records";
import { useFitRun } from "../hooks/useFitRun";
import { FitResultView } from "./FitResultView";
import { SaveButton } from "./SaveButton";

type Kind = "service" | "interarrival";

/** "Ajustar distribuição" (Fase 13): cola ou importa uma amostra de tempos e compara exponencial, Erlang-k, lognormal, Weibull e uniforme. */
export function FitTab() {
  const { state, run, cancel } = useFitRun();
  const [text, setText] = useState("");
  const [kind, setKind] = useState<Kind>("service");
  const [bootstrap, setBootstrap] = useState("");
  const [seed, setSeed] = useState("");
  const [message, setMessage] = useState<string | null>(null);
  const file = useRef<HTMLInputElement>(null);

  const busy = state.status === "loading";
  const parsed = parseSampleText(text);

  const onFile = async (e: ChangeEvent<HTMLInputElement>) => {
    const picked = e.target.files?.[0];
    e.target.value = "";
    if (!picked) return;
    if (picked.size > MAX_SAMPLE_BYTES) {
      setMessage(`O arquivo passa do limite de ${MAX_SAMPLE_BYTES / (1024 * 1024)} MB (o mesmo do envio de CSV).`);
      return;
    }
    const { values, ignored } = parseSampleFile(await readFileText(picked));
    setText(values.join("\n"));
    setMessage(`${values.length.toLocaleString("pt-BR")} valores lidos de ${picked.name}${ignored ? `; ${ignored} linha(s) ignorada(s) por não serem número` : ""}.`);
  };

  const submit = () => {
    if (parsed.values.length < MIN_SAMPLE) {
      setMessage(`Informe pelo menos ${MIN_SAMPLE} valores positivos (há ${parsed.values.length}).`);
      return;
    }
    setMessage(null);
    const body: Record<string, unknown> = { sample: parsed.values, kind };
    if (bootstrap.trim() !== "") body.bootstrap = Number(bootstrap);
    if (seed.trim() !== "") body.seed = Number(seed);
    void run(body);
  };

  return (
    <div className="fit-tab">
      <section className="panel">
        <h2>Ajustar distribuição</h2>
        <p className="sub">
          Cole ou importe uma amostra de tempos (um valor por linha, em segundos). O ajuste é por máxima verossimilhança, com AIC e p-valor de
          aderência por Monte Carlo (não é o KS simples, que erra quando os parâmetros saem da própria amostra).
        </p>
        <div className="field">
          <label htmlFor="fit-sample">Amostra</label>
          <textarea id="fit-sample" rows={8} value={text} onChange={(e) => setText(e.target.value)} placeholder={"0,82\n1,15\n0,47\n…"} />
          <span className="hint">
            {parsed.values.length.toLocaleString("pt-BR")} valores{parsed.ignored ? ` (${parsed.ignored} entrada(s) ignorada(s))` : ""}
          </span>
        </div>
        <div className="field inline">
          <button type="button" className="btn" onClick={() => file.current?.click()} disabled={busy}>Importar CSV ou TXT</button>
          <input ref={file} type="file" accept=".csv,.txt,text/csv,text/plain" hidden aria-label="Importar arquivo da amostra" onChange={(e) => void onFile(e)} />
        </div>
        <div className="field">
          <label htmlFor="fit-kind">O que a amostra representa</label>
          <select id="fit-kind" value={kind} onChange={(e) => setKind(e.target.value as Kind)}>
            <option value="service">Tempos de serviço</option>
            <option value="interarrival">Tempos entre chegadas</option>
          </select>
        </div>
        <div className="field">
          <label htmlFor="fit-b">Réplicas do p-valor (B)</label>
          <input id="fit-b" inputMode="numeric" value={bootstrap} onChange={(e) => setBootstrap(e.target.value)} placeholder="200 (automático)" />
          <span className="hint">De 20 a 2.000, ou 0 para ajustar sem p-valor. Em branco: 200, ou o que o tamanho da amostra permite.</span>
        </div>
        <div className="field">
          <label htmlFor="fit-seed">Semente (opcional)</label>
          <input id="fit-seed" inputMode="numeric" value={seed} onChange={(e) => setSeed(e.target.value)} placeholder="sorteada" />
        </div>
        {message && <p className="note" role="status">{message}</p>}
        <div className="actions">
          <button type="button" className="btn primary" onClick={submit} disabled={busy}>Ajustar</button>
          {busy && <button type="button" className="btn" onClick={cancel}>Cancelar</button>}
        </div>
      </section>

      <section className="panel">
        {state.status === "idle" && <p className="sub">O resultado aparece aqui.</p>}
        {state.status === "loading" && (
          <div className="state" role="status" aria-live="polite">
            <div className="spinner" aria-hidden="true" />
            <p>Ajustando… {state.completed} de {state.total || 5} candidatas{state.bootstrap ? ` (B = ${state.bootstrap})` : ""}</p>
          </div>
        )}
        {state.status === "error" && (
          <div className="state state-error" role="alert">
            <h3>{state.error.code === "file_too_large" ? "Amostra grande demais" : "Não foi possível ajustar"}</h3>
            <p>{state.error.message}</p>
          </div>
        )}
        {state.status === "success" && (
          <>
            <SaveButton suggestedTitle={fitTitle(state.result)} build={(t) => fitRecord(state.request, state.result, t ?? fitTitle(state.result))} />
            <FitResultView result={state.result} />
          </>
        )}
      </section>
    </div>
  );
}
