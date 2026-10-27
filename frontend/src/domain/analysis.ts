/**
 * Fase 13: pedidos e leitura de amostras para os gráficos de distribuição e o ajuste.
 *
 * O limite de tamanho é o do envio de CSV da Fase 7 (10 MiB), o mesmo que a API aplica ao corpo.
 */
import type { ModelKey, ViewResult } from "./types";

export const MAX_SAMPLE_BYTES = 10 * 1024 * 1024;
export const MIN_SAMPLE = 10;

/** O Erlang-B é um sistema de perda: não tem fila, então não tem P(Wq > t) nem Wq. */
export const hasDistributions = (model: ModelKey): boolean => model !== "erlangb";

/** Configuração do Laboratório no formato dos pedidos de /api/analysis (serviço aninhado em `service`). */
export function analysisConfig(result: ViewResult): Record<string, unknown> {
  const { params, modelKey } = result;
  const body: Record<string, unknown> = { model: modelKey, lambda: params.lambda };
  if (params.service) body.service = { distribution: params.service.distribution, ...params.service.values };
  else body.mu = params.mu;
  if (params.servers !== undefined) body.servers = params.servers;
  if (params.capacity !== undefined) body.capacity = params.capacity;
  return body;
}

export interface ParsedSample {
  values: number[];
  /** Entradas que não são número (ignoradas); a tela avisa quantas. */
  ignored: number;
}

/** Aceita números separados por espaço, quebra de linha, ponto e vírgula ou vírgula; vírgula decimal (1,5) também. */
export function parseSampleText(text: string): ParsedSample {
  const values: number[] = [];
  let ignored = 0;
  for (const raw of text.split(/[\s;]+/)) {
    if (!raw) continue;
    const parts = (raw.match(/,/g) ?? []).length > 1 ? raw.split(",") : [raw.replace(",", ".")];
    for (const part of parts) {
      if (!part) continue;
      const n = Number(part);
      if (Number.isFinite(n)) values.push(n); else ignored += 1;
    }
  }
  return { values, ignored };
}

/** Primeira coluna de uma linha de CSV: separa por ; ou tab; a vírgula só separa se não for decimal (1,5). */
function firstField(line: string): string {
  const field = line.split(/[;\t]/)[0].trim();
  if (/^-?\d+,\d+$/.test(field)) return field.replace(",", ".");
  return field.split(",")[0].trim();
}

/** CSV/TXT importado: usa a primeira coluna de cada linha e pula o cabeçalho e as linhas que não são número. */
export function parseSampleFile(text: string): ParsedSample {
  const values: number[] = [];
  let ignored = 0;
  text.replace(/^\ufeff/, "").split(/\r?\n/).forEach((line, i) => {
    if (!line.trim()) return;
    const field = firstField(line);
    const n = Number(field);
    if (field !== "" && Number.isFinite(n)) values.push(n);
    else if (!(i === 0 && values.length === 0)) ignored += 1;     // a primeira linha não numérica é o cabeçalho
  });
  return { values, ignored };
}

export const formatP = (p: number): string => (p < 0.001 ? "< 0,001" : p.toFixed(3).replace(".", ","));

/** Lê um arquivo como texto; usa FileReader quando `File.text()` não existe (jsdom, navegadores antigos). */
export function readFileText(file: Blob): Promise<string> {
  if (typeof file.text === "function") return file.text();
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => resolve(String(reader.result ?? ""));
    reader.onerror = () => reject(reader.error ?? new Error("Falha ao ler o arquivo."));
    reader.readAsText(file);
  });
}
