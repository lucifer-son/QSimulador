import { IconCheck, IconCopy } from "@tabler/icons-react";
import { useState } from "react";
import { formatInteger, formatNumber } from "../domain/format";
import type { ViewResult } from "../domain/types";

function CopyButton({ text, label }: { text: string; label: string }) {
  const [copied, setCopied] = useState(false);
  const copy = async () => {
    try {
      await navigator.clipboard.writeText(text);
      setCopied(true);
      window.setTimeout(() => setCopied(false), 1500);
    } catch {
      setCopied(false); // sem permissão de área de transferência
    }
  };
  return (
    <button type="button" className="btn btn-small" onClick={() => void copy()}>
      {copied ? <IconCheck size={14} aria-hidden="true" /> : <IconCopy size={14} aria-hidden="true" />}
      {copied ? "Copiado" : label}
    </button>
  );
}

export function DetailsTab({ result }: { result: ViewResult }) {
  const rows: [string, string][] = [
    ["Modelo", result.modelLabel],
    ["Chegadas λ", formatNumber(result.params.lambda)],
    ["Serviço μ", formatNumber(result.params.mu)],
    ["Servidores c", formatInteger(result.servers)],
    ["Capacidade K", result.capacity === null ? "ilimitada" : formatInteger(result.capacity)],
  ];
  if (result.action !== "calculate") {
    rows.push(
      ["Tempo simulado", `${formatNumber(result.simulationTime ?? 0)} s`],
      ["Warm-up", `${formatNumber(result.warmupTime ?? 0)} s`],
      ["Réplicas", formatInteger(result.replications ?? 0)],
      ["Nível de confiança", `${Math.round((result.confidenceLevel ?? 0.95) * 100)}%`],
    );
  }
  const json = JSON.stringify(result.raw, null, 2);

  return (
    <div className="block">
      <dl className="details">
        {rows.map(([term, value]) => (
          <div key={term}><dt>{term}</dt><dd>{value}</dd></div>
        ))}
        {result.seed !== undefined && (
          <div>
            <dt>Semente</dt>
            <dd>{result.seed} <CopyButton text={String(result.seed)} label="Copiar" /></dd>
          </div>
        )}
      </dl>
      <details className="json">
        <summary>Resposta completa da API</summary>
        <div className="json-actions"><CopyButton text={json} label="Copiar JSON" /></div>
        <pre>{json}</pre>
      </details>
    </div>
  );
}
