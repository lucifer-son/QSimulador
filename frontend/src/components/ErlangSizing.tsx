import { IconCalculator } from "@tabler/icons-react";
import { useState } from "react";
import { ApiError, postJson } from "../api/client";
import type { components } from "../api/schema";
import { formatPercentNumber } from "../domain/format";
import { parseNumber } from "../domain/number";
import { TextField } from "./TextField";

type Sizing = components["schemas"]["ErlangBSizeResponse"];

interface Props {
  lambda: string;
  mu: string;
  onApply: (servers: number) => void;
}

/**
 * Dimensionamento do Erlang-B: dado o bloqueio máximo aceitável, sugere o menor número de
 * servidores (linhas, canais). Usa λ e μ do formulário e deixa o usuário aplicar o resultado.
 */
export function ErlangSizing({ lambda, mu, onApply }: Props) {
  const [target, setTarget] = useState("1");
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<Sizing | null>(null);
  const [busy, setBusy] = useState(false);

  const run = async () => {
    setError(null);
    setResult(null);
    const lam = parseNumber(lambda);
    const rate = parseNumber(mu);
    const pct = parseNumber(target);
    if (![lam, rate, pct].every(Number.isFinite)) {
      setError("Informe λ, μ e o bloqueio alvo como números.");
      return;
    }
    setBusy(true);
    try {
      setResult(await postJson<Sizing>("/api/models/erlangb/size", { lambda: lam, mu: rate, target_blocking: pct / 100 }));
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Erro inesperado.");
    } finally {
      setBusy(false);
    }
  };

  return (
    <section className="sizing" aria-label="Dimensionamento por bloqueio alvo">
      <h2 className="group-title">Dimensionar</h2>
      <TextField
        id="erlang-target" label="Bloqueio alvo (%)" value={target} error={error ?? undefined}
        hint="Quantos % de chamadas perdidas você aceita" onChange={(v) => { setTarget(v); setError(null); }}
      />
      <button type="button" className="btn btn-small" disabled={busy} onClick={() => void run()}>
        <IconCalculator size={14} aria-hidden="true" /> Sugerir c
      </button>
      {result && (
        <p className="sizing-result" role="status">
          Com <strong>c = {result.servers}</strong> o bloqueio é {formatPercentNumber(result.blocking * 100, 2)}
          {result.blocking_previous !== null && `; com c = ${result.servers - 1} seria ${formatPercentNumber(result.blocking_previous * 100, 2)}`}.
          {" "}
          <button type="button" className="btn btn-small" onClick={() => onApply(result.servers)}>
            Usar c = {result.servers}
          </button>
        </p>
      )}
    </section>
  );
}
