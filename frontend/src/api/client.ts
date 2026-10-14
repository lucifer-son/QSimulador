import type { components } from "./schema";

type ErrorResponse = components["schemas"]["ErrorResponse"];

export type ApiErrorCode =
  | "unstable_system"
  | "invalid_parameter"
  | "invalid_request"
  | "insufficient_sample"
  | "invalid_dataset"
  | "file_too_large"
  | "network"
  | "http"
  | "aborted";

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

async function send<T>(path: string, init: RequestInit, signal?: AbortSignal): Promise<T> {
  let response: Response;
  try {
    response = await fetch(`${BASE_URL}${path}`, { ...init, signal });
  } catch (error) {
    const aborted = signal?.aborted || (error instanceof DOMException && error.name === "AbortError");
    if (aborted) throw new ApiError("aborted", "Execução cancelada.");
    throw new ApiError("network", "Não foi possível conectar à API. Confira se o servidor está no ar.");
  }

  if (response.ok) return (await response.json()) as T;

  let payload: Partial<ErrorResponse> | null = null;
  try {
    payload = (await response.json()) as Partial<ErrorResponse>;
  } catch {
    payload = null; // resposta sem corpo JSON
  }
  const code = payload?.code as ApiErrorCode | undefined;
  // 422: erro de validação; 413: arquivo acima do limite (envio de CSV).
  if ((response.status === 422 || response.status === 413) && code && API_CODES.includes(code) && typeof payload?.message === "string") {
    throw new ApiError(code, payload.message, payload.fields ?? undefined);
  }
  throw new ApiError("http", `A API respondeu com erro ${response.status}.`);
}

export const postJson = <T>(path: string, body: unknown, signal?: AbortSignal): Promise<T> =>
  send<T>(path, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) }, signal);

/** Envio de arquivo (multipart): o navegador define o Content-Type com o separador. */
export const postForm = <T>(path: string, form: FormData, signal?: AbortSignal): Promise<T> =>
  send<T>(path, { method: "POST", body: form }, signal);
