import type { components } from "./schema";

type ErrorResponse = components["schemas"]["ErrorResponse"];

export type ApiErrorCode =
  | "unstable_system"
  | "invalid_parameter"
  | "invalid_request"
  | "insufficient_sample"
  | "network"
  | "http"
  | "aborted";

export interface FieldIssue {
  field: string;
  message: string;
}

const API_CODES: ApiErrorCode[] = [
  "unstable_system", "invalid_parameter", "invalid_request", "insufficient_sample",
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

export async function postJson<T>(path: string, body: unknown, signal?: AbortSignal): Promise<T> {
  let response: Response;
  try {
    response = await fetch(`${BASE_URL}${path}`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
      signal,
    });
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
  if (response.status === 422 && code && API_CODES.includes(code) && typeof payload?.message === "string") {
    throw new ApiError(code, payload.message, payload.fields ?? undefined);
  }
  throw new ApiError("http", `A API respondeu com erro ${response.status}.`);
}
