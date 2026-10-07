import { vi } from "vitest";
import errorInvalidParameter from "./fixtures/error-invalid-parameter.json";
import errorInvalidRequest from "./fixtures/error-invalid-request.json";
import errorUnstable from "./fixtures/error-unstable.json";
import mm1Calculate from "./fixtures/mm1-calculate.json";
import mm1Compare from "./fixtures/mm1-compare.json";
import mm1Simulate from "./fixtures/mm1-simulate.json";
import mmcCalculate from "./fixtures/mmc-calculate.json";
import mmcCompare from "./fixtures/mmc-compare.json";
import mmcSimulate from "./fixtures/mmc-simulate.json";
import mmckCalculate from "./fixtures/mmck-calculate.json";
import mmckCompare from "./fixtures/mmck-compare.json";
import mmckCompare1Rep from "./fixtures/mmck-compare-1rep.json";
import mmckSimulate from "./fixtures/mmck-simulate.json";
import type { ThemeColors } from "../hooks/useThemeColors";

/** Respostas reais da API, gravadas em arquivos (ver src/test/fixtures). */
export const fixtures = {
  errorInvalidParameter, errorInvalidRequest, errorUnstable,
  mm1Calculate, mm1Compare, mm1Simulate,
  mmcCalculate, mmcCompare, mmcSimulate,
  mmckCalculate, mmckCompare, mmckCompare1Rep, mmckSimulate,
};

export const colors: ThemeColors = {
  text: "#111111", textSecondary: "#222222", textMuted: "#333333",
  border: "#444444", accent: "#0000ff", danger: "#ff0000",
};

/** Cópia profunda, para um teste poder alterar a fixture sem afetar os outros. */
export function clone<T>(value: T): T {
  return JSON.parse(JSON.stringify(value)) as T;
}

export interface FakeReply { status?: number; body: unknown }
export type FakeHandler = (url: string, body: Record<string, unknown>) => FakeReply | Promise<FakeReply>;

/** Substitui o fetch global; devolve o mock para inspecionar as chamadas. */
export function mockFetch(handler: FakeHandler) {
  const fn = vi.fn(async (url: string, init?: RequestInit) => {
    const body = init?.body ? (JSON.parse(String(init.body)) as Record<string, unknown>) : {};
    const reply = await handler(url, body);
    return new Response(JSON.stringify(reply.body), {
      status: reply.status ?? 200,
      headers: { "Content-Type": "application/json" },
    });
  });
  vi.stubGlobal("fetch", fn);
  return fn;
}

/** fetch que nunca responde, só rejeita quando a requisição é cancelada. */
export function mockPendingFetch() {
  const fn = vi.fn(
    (_url: string, init?: RequestInit) =>
      new Promise<Response>((_resolve, reject) => {
        init?.signal?.addEventListener("abort", () => reject(new DOMException("Aborted", "AbortError")));
      }),
  );
  vi.stubGlobal("fetch", fn);
  return fn;
}
