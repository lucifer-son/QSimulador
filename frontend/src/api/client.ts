import type { components } from "./schema";

type ErrorResponse = components["schemas"]["ErrorResponse"];

export type ApiErrorCode =
  | "unstable_system"
  | "invalid_parameter"
  | "invalid_request"
  | "insufficient_sample"
  | "invalid_dataset"
  | "file_too_large"
  | RecordsErrorCode
  | "network"
  | "http"
  | "aborted";

/** Erros próprios do histórico (/api/records). */
export type RecordsErrorCode =
  | "persistence_disabled"
  | "database_unavailable"
  | "record_not_found"
  | "record_too_large"
  | "record_limit_reached"
  | "invalid_client_id"
  | "invalid_record";

const RECORDS_CODES: RecordsErrorCode[] = [
  "persistence_disabled", "database_unavailable", "record_not_found", "record_too_large",
  "record_limit_reached", "invalid_client_id", "invalid_record",
];

export interface FieldIssue {
  field: string;
  message: string;
}

const API_CODES: ApiErrorCode[] = [
  "unstable_system", "invalid_parameter", "invalid_request", "insufficient_sample",
  "invalid_dataset", "file_too_large",
];

export class ApiError extends Error {
  constructor(
    public code: ApiErrorCode,
    message: string,
    public fields?: FieldIssue[],
  ) {
    super(message);
    this.name = "ApiError";
  }
}

// Vazio = mesma origem (o proxy do Vite cuida do desenvolvimento).
const BASE_URL: string = (import.meta.env.VITE_API_BASE_URL as string | undefined) ?? "";

export async function send<T>(path: string, init: RequestInit, signal?: AbortSignal): Promise<T> {
  const response = await fetchApi(path, init, signal);
  if (response.ok) return (response.status === 204 ? undefined : await response.json()) as T;
  throw await apiErrorFrom(response);
}

/** Converte uma resposta de erro da API (422, 413, 404, 409, 503...) em ApiError. */
export async function apiErrorFrom(response: Response): Promise<ApiError> {
  let payload: Partial<ErrorResponse> | null = null;
  try {
    payload = (await response.json()) as Partial<ErrorResponse>;
  } catch {
    payload = null; // resposta sem corpo JSON
  }
  const code = payload?.code as ApiErrorCode | undefined;
  // 422: erro de validação; 413: arquivo acima do limite (envio de CSV).
  if (
    (response.status === 422 || response.status === 413) && code
    && (API_CODES.includes(code) || (RECORDS_CODES as string[]).includes(code))
    && typeof payload?.message === "string"
  ) {
    return new ApiError(code, payload.message, payload.fields ?? undefined);
  }
  // Histórico: 404 (não existe), 409 (limite de registros) e 503 (sem banco) também trazem {code, message}.
  if (
    [404, 409, 503].includes(response.status) && code && (RECORDS_CODES as string[]).includes(code)
    && typeof payload?.message === "string"
  ) {
    return new ApiError(code, payload.message);
  }
  return new ApiError("http", `A API respondeu com erro ${response.status}.`);
}

/** fetch que traduz falha de rede e cancelamento em ApiError (usado também pelos envios que não são JSON). */
export async function fetchApi(path: string, init: RequestInit, signal?: AbortSignal): Promise<Response> {
  try {
    return await fetch(`${BASE_URL}${path}`, { ...init, signal });
  } catch (error) {
    const aborted = signal?.aborted || (error instanceof DOMException && error.name === "AbortError");
    if (aborted) throw new ApiError("aborted", "Execução cancelada.");
    throw new ApiError("network", "Não foi possível conectar à API. Confira se o servidor está no ar.");
  }
}

export const postJson = <T>(path: string, body: unknown, signal?: AbortSignal): Promise<T> =>
  send<T>(path, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) }, signal);

/** Envio de arquivo (multipart): o navegador define o Content-Type com o separador. */
export const postForm = <T>(path: string, form: FormData, signal?: AbortSignal): Promise<T> =>
  send<T>(path, { method: "POST", body: form }, signal);
